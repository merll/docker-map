# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from collections import defaultdict
from hashlib import md5

import posixpath
import unittest
import responses

from dockermap import DEFAULT_COREIMAGE, DEFAULT_BASEIMAGE
from dockermap.map.config.client import ClientConfiguration
from dockermap.map.config.main import ContainerMap
from dockermap.map.config.utils import get_map_config_ids
from dockermap.map.input import ExecCommand, ExecPolicy, MapConfigId, ItemType, UsedVolume
from dockermap.map.policy import ConfigFlags
from dockermap.map.policy.base import BasePolicy
from dockermap.map.policy.utils import get_shared_volume_path
from dockermap.map.state import INITIAL_START_TIME, State, StateFlags
from dockermap.map.state.base import DependencyStateGenerator, DependentStateGenerator, SingleStateGenerator
from dockermap.map.state.update import UpdateStateGenerator
from dockermap.map.state.utils import merge_dependency_paths
from dockermap.utils import format_image_tag

from tests import MAP_DATA_2, CLIENT_DATA_1, CLIENT_DATA_2


URL_PREFIXES = ['http+docker://localunixsocket/v{0}'.format(v) for v in (CLIENT_DATA_1['version'],
                                                                         CLIENT_DATA_2['version'])]

P_STATE_INITIAL = 0
P_STATE_RUNNING = 1
P_STATE_RESTARTING = 2
P_STATE_EXITED_0 = 3
P_STATE_EXITED_127 = 4
STATE_RESULTS = {
    P_STATE_INITIAL: {
        'Running': False,
        'Restarting': False,
        'Pid': 0,
        'ExitCode': 0,
        'StartedAt': INITIAL_START_TIME,
    },
    P_STATE_RESTARTING: {
        'Running': False,
        'Restarting': True,
        'Pid': 0,
        'ExitCode': 255,
        'StartedAt': "2016-02-05T20:14:04.655843958Z",
    },
    P_STATE_RUNNING: {
        'Running': True,
        'Restarting': False,
        'Pid': 1,
        'ExitCode': 0,
        'StartedAt': "2016-02-05T20:14:04.655843958Z",
    },
    P_STATE_EXITED_0: {
        'Running': False,
        'Restarting': False,
        'Pid': 0,
        'ExitCode': 0,
        'StartedAt': "2016-02-05T20:14:04.655843958Z",
    },
    P_STATE_EXITED_127: {
        'Running': False,
        'Restarting': False,
        'Pid': 0,
        'ExitCode': -127,
        'StartedAt': "2016-02-05T20:14:04.655843958Z",
    },
}


def _get_hash(main, *args):
    h = md5(main)
    for a in args:
        h.update(a)
    return h.hexdigest()


def get_image_id(image_name):
    return _get_hash('image_name', image_name)


def get_container_id(container_name):
    return _get_hash('container', container_name)


def get_network_id(network_name):
    return _get_hash('network', network_name)


def get_endpoint_id(network_name, container_id):
    return _get_hash('network-endpoint', network_name, container_id)


def get_invalid_endpoint_id(network_name, container_id):
    return 'invalid-{0}'.format(get_endpoint_id(network_name, container_id))


def _container(config_name, p_state=P_STATE_RUNNING, instances=None, attached_volumes_valid=True,
               instance_volumes_valid=True, **kwargs):
    return config_name, p_state, instances, attached_volumes_valid, instance_volumes_valid, kwargs


def _network(config_name, **kwargs):
    return config_name, kwargs


def _add_container_list(rsps, container_names):
    results = [
        {'Id': get_container_id(name), 'Names': ['/{0}'.format(name)]}
        for name in container_names
    ]
    for prefix in URL_PREFIXES:
        rsps.add('GET', '{0}/containers/json'.format(prefix), content_type='application/json', json=results)


def _add_network_list(rsps, network_names):
    results = [
        {'Id': get_network_id(name), 'Name': name}
        for name in network_names
    ]
    for prefix in URL_PREFIXES:
        rsps.add('GET', '{0}/networks'.format(prefix), content_type='application/json', json=results)


def _add_volume_list(rsps, volume_names):
    results = {
        'Volumes': [
            {'Name': name} for name in volume_names
        ] or None,
        'Warnings': None,
    }
    for prefix in URL_PREFIXES:
        rsps.add('GET', '{0}/volumes'.format(prefix), content_type='application/json', json=results)


def _add_image_list(rsps, image_names):
    image_list = [
        {
            'RepoTags': ['{0}:latest'.format(i_name), '{0}:1.0'.format(i_name)] if ':' not in i_name else [i_name],
            'Id': i_id,
        }
        for i_id, i_name in image_names
    ]
    for prefix in URL_PREFIXES:
        rsps.add('GET', '{0}/images/json'.format(prefix), content_type='application/json', json=image_list)
    for image in image_list:
        for r_tag in image['RepoTags']:
            for prefix in URL_PREFIXES:
                rsps.add('GET', '{0}/images/{1}/json'.format(prefix, r_tag), content_type='application/json',
                         json=image)
    for prefix in URL_PREFIXES:
        rsps.add('POST', '{0}/images/create'.format(prefix), content_type='application/json')


def _get_container_mounts(config_id, container_map, c_config, named_volumes, valid):
    if valid:
        path_prefix = '/valid'
    else:
        path_prefix = '/invalid_{0}'.format(config_id.config_name)
    for a in c_config.attaches:
        if isinstance(a, UsedVolume):
            c_path = a.path
        else:
            c_path = container_map.volumes[a.name].default_path
        yield {
            'Type': 'volume',
            'Source': posixpath.join(path_prefix, 'attached', a.name),
            'Destination': c_path,
            'Name': '{0}.{1}.{2}'.format(config_id.map_name, config_id.config_name, a.name)
                    if named_volumes else '',
            'RW': True
        }
    if config_id.config_type == ItemType.CONTAINER:
        for vol in c_config.binds:
            c_path, h_path = get_shared_volume_path(container_map, vol, config_id.instance_name)
            yield {
                'Type': 'bind',
                'Source': posixpath.join(path_prefix, h_path),
                'Destination': c_path,
                'RW': not vol.readonly,
            }
        for s in c_config.shares:
            yield {
                'Type': 'volume',
                'Source': posixpath.join(path_prefix, 'shared', s),
                'Destination': s,
                'Name': _get_hash('shared-volume', path_prefix, s) if named_volumes else '',
                'RW': True,
            }
        for vol in c_config.uses:
            c, __, i = vol.name.partition('.')
            c_ref = container_map.get_existing(c)
            if c_ref:
                attached_volumes = {a.name: a for a in c_ref.attaches}
                if i and i in attached_volumes:
                    instance_volume = attached_volumes[i]
                    if isinstance(instance_volume, UsedVolume):
                        c_path = instance_volume.path
                    else:
                        c_path = container_map.volumes[i].default_path
                    yield {
                        'Type': 'volume',
                        'Source': posixpath.join(path_prefix, 'attached', i) if not named_volumes else '',
                        'Destination': c_path,
                        'Name': '{0}.{1}'.format(config_id.map_name, vol.name) if named_volumes else '',
                        'RW': not vol.readonly,
                    }
                elif not i or i in c_ref.instances:
                    for r_mount in _get_container_mounts(MapConfigId(config_id.config_type, config_id.map_name, c, i),
                                                         container_map, c_ref, named_volumes, valid):
                        yield r_mount
                else:
                    raise ValueError("Invalid uses declaration in {0}: volume for {1} not found.".format(config_id.config_name, vol))
            else:
                raise ValueError("Invalid uses declaration in {0}: configuration for {1} not found.".format(config_id.config_name, vol))


def _add_container_inspect(rsps, config_id, container_name, container_map, c_config, state, image_id, named_volumes,
                           volumes_valid, links_valid=True, network_ep_valid=True, network_link_valid=True,
                           skip_network=None, extra_network=False, **kwargs):
    config_type = config_id.config_type
    container_id = get_container_id(container_name)
    ports = defaultdict(list)
    host_config = {}
    network_settings = {}
    config_dict = {
        'Env': None,
        'Cmd': [],
        'Entrypoint': [],
    }
    host_config['NetworkMode'] = 'default'  # TODO: Vary.
    if config_type == ItemType.CONTAINER:
        for ex in c_config.exposes:
            ex_port = '{0}/tcp'.format(ex.exposed_port)
            if ex.host_port:
                if ex.interface:
                    ip = CLIENT_DATA_1['interfaces'][ex.interface]
                else:
                    ip = '0.0.0.0'
                ports[ex_port].append({
                    'HostIp': ip,
                    'HostPort': '{0}'.format(ex.host_port)
                })
            else:
                ports[ex_port].extend(())
        if links_valid:
            links_format = '/{0}.{1}:/{2}/{3}'
        else:
            links_format = '/{0}.{1}:/{2}/invalid-{3}'
        host_config['Links'] = [
            links_format.format(config_id.map_name, link.container, container_name,
                                link.alias or BasePolicy.get_hostname(link.container))
            for link in c_config.links
        ]
        networks = {}
        network_ep_func = get_endpoint_id if network_ep_valid else get_invalid_endpoint_id
        default_aliases = ['{0}_alias'.format(config_id.config_name)]
        if c_config.network_mode != 'none':  # TODO: Vary.
            for n in c_config.networks:
                if n.network_name == skip_network:
                    continue
                network_name = '{0}.{1}'.format(config_id.map_name, n.network_name)
                if n.links and network_link_valid:
                    link_list = ['{0}.{1}'.format(config_id.map_name, nl) for nl in n.links]
                else:
                    link_list = None
                networks[network_name] = {
                    'Links': link_list,
                    'Aliases': n.aliases or default_aliases,
                    'NetworkID': get_network_id(network_name),
                    'EndpointID': network_ep_func(network_name, container_id),
                }
            if not c_config.networks:
                networks['bridge'] = {
                    'Links': None,
                    'Aliases': default_aliases,
                    'NetworkID': get_network_id('bridge'),
                    'EndpointID': network_ep_func('bridge', container_id),
                }
            if extra_network:
                networks['extra'] = {
                    'Links':  None,
                    'Aliases': default_aliases,
                    'NetworkID': get_network_id('extra'),
                    'EndpointID': network_ep_func('extra', container_id),
                }
        else:
            config_dict['NetworkDisabled'] = True
        network_settings = {
            'Ports': ports,
            'Networks': networks,
        }
    else:
        config_dict['NetworkDisabled'] = True
    name_list = [container_name]
    results = {
        'Id': container_id,
        'Names': name_list,
        'State': STATE_RESULTS[state],
        'Image': image_id,
        'Mounts': list(_get_container_mounts(config_id, container_map, c_config, named_volumes, volumes_valid)),
        'HostConfig': host_config,
        'Config': config_dict,
        'NetworkSettings': network_settings,
    }
    exec_results = {
        'Processes': [
            [cmd_i, cmd.user, cmd.cmd]
            for cmd_i, cmd in enumerate(c_config.exec_commands)
        ],
    }
    results.update(kwargs)
    for i_id in (container_name, container_id):
        for prefix in URL_PREFIXES:
            rsps.add('GET', '{0}/containers/{1}/json'.format(prefix, i_id),
                     content_type='application/json',
                     json=results)
            rsps.add('GET', '{0}/containers/{1}/top'.format(prefix, i_id),
                     content_type='application/json',
                     json=exec_results)
    return container_name


def _add_network_inspect(rsps, network_name, n_config, containers, **kwargs):
    network_id = get_network_id(network_name)
    container_ids = [(get_container_id(c_name), c_name) for c_name in containers]
    if n_config:
        driver = n_config.driver
        internal = n_config.internal
    else:
        driver = network_name if network_name != 'none' else 'null'
        internal = False
    results = {
        'Id': network_id,
        'Name': network_name,
        'Driver': driver,
        'Internal': internal,
        'Options': {},
        'Containers': {
            c_id: {
                'Name': c_name,
                'EndpointID': get_endpoint_id(network_name, c_id),
            }
            for c_id, c_name in container_ids
        },
    }
    results.update(kwargs)
    for i_id in (network_name, network_id):
        for prefix in URL_PREFIXES:
            rsps.add('GET', '{0}/networks/{1}'.format(prefix, i_id),
                     content_type='application/json',
                     json=results)


def _add_volume_inspect(rsps, volume_name, **kwargs):
    results = {
        'Driver': 'local',
        'Mountpoint': '/docker/volumes/{0}/_data'.format(volume_name),
        'Name': volume_name,
        'Options': {},
    }
    results.update(kwargs)
    for prefix in URL_PREFIXES:
        rsps.add('GET', '{0}/volumes/{1}'.format(prefix, volume_name),
                 content_type='application/json',
                 json=results)


def _get_single_state(sg, config_ids):
    states = [s
              for s in sg.get_states(config_ids)
              if s.config_id.config_type == ItemType.CONTAINER]
    return states[-1]


def _get_states_dict(sl):
    cd = {}
    nd = {}
    vd = {}
    imd = {}
    for s in sl:
        config_id = s.config_id
        if config_id.config_type == ItemType.CONTAINER:
            cd[(config_id.config_name, config_id.instance_name)] = s
        elif config_id.config_type == ItemType.VOLUME:
            vd[(config_id.config_name, config_id.instance_name)] = s
        elif config_id.config_type == ItemType.NETWORK:
            nd[config_id.config_name] = s
        elif config_id.config_type == ItemType.IMAGE:
            imd[(config_id.config_name, config_id.instance_name)] = s
        else:
            raise ValueError("Invalid configuration type.", config_id.config_type)
    return {
        'containers': cd,
        'volumes': vd,
        'networks': nd,
        'images': imd,
    }


class TestPolicyStateGenerators(unittest.TestCase):
    def setUp(self):
        self.map_name = map_name = 'main'
        self.sample_map = sample_map = ContainerMap('main', MAP_DATA_2,
                                                    use_attached_parent_name=True).get_extended_map()
        self.sample_map.repository = None
        self.sample_client_config1 = client_config1 = ClientConfiguration(**CLIENT_DATA_1)
        self.sample_client_config2 = client_config2 = ClientConfiguration(**CLIENT_DATA_2)
        self.policy = BasePolicy({map_name: sample_map}, {'__default__': client_config1})
        self.policy_legacy = BasePolicy({map_name: sample_map}, {'__default__': client_config2})
        self.server_config_id = self._config_id('server')
        all_images = set(format_image_tag(sample_map.get_image(c_config.image or c_name))
                         for c_name, c_config in sample_map)
        all_images.add(DEFAULT_COREIMAGE)
        all_images.add(DEFAULT_BASEIMAGE)
        self.images = [(get_image_id(image_name), image_name)
                       for image_name in all_images]

    def _config_id(self, config_name, instance=None):
        return [MapConfigId(ItemType.CONTAINER, self.map_name, config_name, instance)]

    def _setup_containers(self, rsps, containers_states, networks=(), use_named_volumes=True):
        container_names = []
        volume_names = []
        network_names = []
        _add_image_list(rsps, self.images)
        image_dict = {name: _id for _id, name in self.images}
        base_image_id = image_dict[DEFAULT_BASEIMAGE]
        network_containers = defaultdict(list)
        for name, state, instances, attached_valid, instances_valid, kwargs in containers_states:
            c_config = self.sample_map.get_existing(name)
            for a in c_config.attaches:
                config_id = MapConfigId(ItemType.VOLUME, self.map_name, name, a.name)
                volume_name = '{0.map_name}.{0.config_name}.{0.instance_name}'.format(config_id)
                if use_named_volumes:
                    _add_volume_inspect(rsps, volume_name)
                    volume_names.append(volume_name)
                else:
                    _add_container_inspect(rsps, config_id, volume_name, self.sample_map, c_config,
                                           P_STATE_EXITED_0, base_image_id, False, attached_valid)
                    container_names.append(volume_name)
            image_name = format_image_tag(self.sample_map.get_image(c_config.image or name))
            image_id = image_dict[image_name]
            for i in instances or c_config.instances or [None]:
                config_id = MapConfigId(ItemType.CONTAINER, self.map_name, name, i)
                if config_id.instance_name:
                    container_name = '{0.map_name}.{0.config_name}.{0.instance_name}'.format(config_id)
                else:
                    container_name = '{0.map_name}.{0.config_name}'.format(config_id)
                _add_container_inspect(rsps, config_id, container_name, self.sample_map, c_config,
                                       state, image_id, use_named_volumes, instances_valid, **kwargs)
                container_names.append(container_name)
                if c_config.networks:
                    for cn in c_config.networks:
                        network_containers[cn.network_name].append(container_name)
                elif c_config.network_mode != 'disabled':
                    network_containers['bridge'].append(container_name)
                    if kwargs.get('extra_network'):
                        network_containers['extra'].append(container_name)
        for n_name, kwargs in networks:
            n_config = self.sample_map.get_existing_network(n_name)
            config_id = MapConfigId(ItemType.NETWORK, self.map_name, n_name)
            network_name = '{0.map_name}.{0.config_name}'.format(config_id)
            _add_network_inspect(rsps, network_name, n_config, network_containers.get(n_name, []), **kwargs)
            network_names.append(network_name)
        for dn_name in ('bridge', 'none', 'host'):
            _add_network_inspect(rsps, dn_name, None, network_containers.get(dn_name, []))
            network_names.append(dn_name)
        _add_container_list(rsps, container_names)
        _add_network_list(rsps, network_names)
        _add_volume_list(rsps, volume_names)

    def _setup_default_containers(self, rsps):
        self._setup_containers(rsps, [
            _container('sub_sub_svc'),
            _container('sub_svc'),
            _container('redis'),
            _container('svc'),
            _container('server'),
        ])

    def test_dependency_states_running(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_default_containers(rsps)
            states = list(DependencyStateGenerator(self.policy, {}).get_states(self.server_config_id))
            instance_base_states = [s.base_state
                                    for s in states
                                    if s.config_id.config_type == ItemType.CONTAINER]
            attached_base_states = [s.base_state
                                    for s in states
                                    if s.config_id.config_type == ItemType.VOLUME]
            self.assertTrue(all(si == State.RUNNING
                                for si in instance_base_states))
            self.assertTrue(all(si == State.PRESENT
                                for si in attached_base_states))
            self.assertTrue(all(s.config_flags == ConfigFlags.DEPENDENT
                                for s in states
                                if s.config_id.config_type == ItemType.CONTAINER and s.config_id.config_name != 'server'))

    def test_single_states_mixed(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis', P_STATE_EXITED_0, instances=['cache']),
                _container('redis', instances=['queue']),
                _container('svc', P_STATE_EXITED_127),
                _container('worker', P_STATE_RESTARTING),
                _container('worker_q2', P_STATE_INITIAL),
            ])
            sg = SingleStateGenerator(self.policy, {})
            cache_state = _get_single_state(sg, self._config_id('redis', 'cache'))
            self.assertEqual(cache_state.base_state, State.PRESENT)
            queue_state = _get_single_state(sg, self._config_id('redis', 'queue'))
            self.assertEqual(queue_state.base_state, State.RUNNING)
            svc_state = _get_single_state(sg, self._config_id('svc'))
            self.assertEqual(svc_state.base_state, State.PRESENT)
            self.assertEqual(svc_state.state_flags & StateFlags.NONRECOVERABLE, StateFlags.NONRECOVERABLE)
            worker_state = _get_single_state(sg, self._config_id('worker'))
            self.assertEqual(worker_state.state_flags & StateFlags.RESTARTING, StateFlags.RESTARTING)
            worker2_state = _get_single_state(sg, self._config_id('worker_q2'))
            self.assertEqual(worker2_state.base_state, State.PRESENT)
            self.assertEqual(worker2_state.state_flags & StateFlags.INITIAL, StateFlags.INITIAL)
            server_states = _get_single_state(sg, self.server_config_id)
            self.assertEqual(server_states.base_state, State.ABSENT)

    def test_single_states_forced_config(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis', instances=['cache', 'queue']),
            ])
            force_update = set(get_map_config_ids('redis', {self.map_name: self.sample_map}, self.map_name))
            sg = SingleStateGenerator(self.policy, {'force_update': force_update})
            cache_state = _get_single_state(sg, self._config_id('redis', 'cache'))
            self.assertEqual(cache_state.state_flags & StateFlags.FORCED_RESET, StateFlags.FORCED_RESET)
            queue_state = _get_single_state(sg, self._config_id('redis', 'queue'))
            self.assertEqual(queue_state.state_flags & StateFlags.FORCED_RESET, StateFlags.FORCED_RESET)

    def test_single_states_forced_instance(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis', instances=['cache', 'queue']),
            ])
            force_update = set(get_map_config_ids('redis', {self.map_name: self.sample_map}, self.map_name, 'cache'))
            sg = SingleStateGenerator(self.policy, {'force_update': force_update})
            cache_state = _get_single_state(sg, self._config_id('redis', 'cache'))
            self.assertEqual(cache_state.state_flags & StateFlags.FORCED_RESET, StateFlags.FORCED_RESET)
            queue_state = _get_single_state(sg, self._config_id('redis', 'queue'))
            self.assertEqual(queue_state.state_flags & StateFlags.NEEDS_RESET, 0)

    def test_dependent_states(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('sub_sub_svc'),
                _container('sub_svc'),
                _container('redis'),
                _container('svc'),
                _container('server'),
                _container('server2'),
                _container('worker'),
                _container('worker_q2'),
            ])
            states = list(DependentStateGenerator(self.policy, {}).get_states(self._config_id('redis', 'cache')))
            instance_base_states = [s.base_state
                                    for s in states
                                    if s.config_id.config_type == ItemType.CONTAINER]
            volume_base_states = [s.base_state
                                  for s in states
                                  if s.config_id.config_type == ItemType.VOLUME]
            self.assertTrue(all(si == State.RUNNING
                                for si in instance_base_states))
            self.assertTrue(all(si == State.PRESENT
                                for si in volume_base_states))
            self.assertTrue(all(s.config_flags == ConfigFlags.DEPENDENT
                                for s in states
                                if not (s.config_id.config_type == ItemType.CONTAINER and s.config_id.config_name == 'redis')))

    def test_update_states_clean(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_default_containers(rsps)
            states = list(UpdateStateGenerator(self.policy, {}).get_states(self.server_config_id))
            valid_order = ['sub_sub_svc', 'sub_svc', 'redis', 'server']
            for c_state in states:
                config_id = c_state.config_id
                if config_id.config_type == ItemType.CONTAINER:
                    config_name = config_id.config_name
                    if config_name in valid_order:
                        self.assertEqual(valid_order[0], config_name)
                        valid_order.pop(0)
                        self.assertEqual(c_state.base_state, State.RUNNING)
                        self.assertEqual(c_state.state_flags, StateFlags.NONE)

    def test_update_states_invalid_attached(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('sub_sub_svc'),
                _container('sub_svc'),
                _container('redis', attached_volumes_valid=False),
                _container('svc'),
                _container('server'),
            ])
            states = _get_states_dict(UpdateStateGenerator(self.policy_legacy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.VOLUME_MISMATCH, StateFlags.VOLUME_MISMATCH)
            for ri in ('cache', 'queue'):
                redis_state = states['containers'][('redis', ri)]
                self.assertEqual(redis_state.base_state, State.RUNNING)
                self.assertEqual(redis_state.state_flags & StateFlags.VOLUME_MISMATCH, StateFlags.VOLUME_MISMATCH)

    def test_update_states_invalid_dependent_instance(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('sub_sub_svc'),
                _container('sub_svc'),
                _container('redis', instance_volumes_valid=False),
                _container('svc'),
                _container('server'),
            ], use_named_volumes=False)
            states = _get_states_dict(UpdateStateGenerator(self.policy_legacy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.NEEDS_RESET, 0)
            for ri in ('cache', 'queue'):
                redis_state = states['containers'][('redis', ri)]
                self.assertEqual(redis_state.base_state, State.RUNNING)
                self.assertEqual(redis_state.state_flags & StateFlags.VOLUME_MISMATCH, StateFlags.VOLUME_MISMATCH)

    def test_update_states_invalid_dependent_instance_attached(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('sub_sub_svc'),
                _container('sub_svc'),
                _container('redis'),
                _container('svc'),
                _container('server', attached_volumes_valid=False),
            ], use_named_volumes=False)
            states = _get_states_dict(UpdateStateGenerator(self.policy_legacy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.VOLUME_MISMATCH, StateFlags.VOLUME_MISMATCH)
            for ri in ('cache', 'queue'):
                redis_state = states['containers'][('redis', ri)]
                self.assertEqual(redis_state.base_state, State.RUNNING)
                self.assertEqual(redis_state.state_flags & StateFlags.NEEDS_RESET, 0)

    def test_update_states_invalid_image(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('sub_sub_svc'),
                _container('sub_svc'),
                _container('redis'),
                _container('svc'),
                _container('server', Image='invalid'),
            ])
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.IMAGE_MISMATCH, StateFlags.IMAGE_MISMATCH)

    def test_update_states_invalid_links(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('sub_sub_svc'),
                _container('sub_svc'),
                _container('redis'),
                _container('svc'),
                _container('server', links_valid=False),
            ])
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.MISSING_LINK, StateFlags.MISSING_LINK)

    def test_update_states_invalid_network_ports(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('sub_sub_svc'),
                _container('sub_svc'),
                _container('redis'),
                _container('svc'),
                _container('server', NetworkSettings=dict(Ports={})),
            ])
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.MISC_MISMATCH, StateFlags.MISC_MISMATCH)

    def test_update_states_network_clean(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('net_svc'),
                _container('server3'),
            ], [
                _network('app_net1'),
                _network('app_net2'),
            ])
            svc_id = self._config_id('server3')
            states = list(UpdateStateGenerator(self.policy, {}).get_states(svc_id))
            self.assertTrue(all(((cs.config_id.config_type in (ItemType.NETWORK, ItemType.VOLUME, ItemType.IMAGE) and
                                  cs.base_state == State.PRESENT) or
                                 (cs.config_id.config_type == ItemType.CONTAINER and
                                  cs.base_state == State.RUNNING)) and
                                cs.state_flags == 0
                                for cs in states))

    def test_update_states_updated_or_missing_network(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('net_svc', skip_network='app_net1'),
                _container('server3', skip_network='app_net1'),
            ], [
                _network('app_net2', Driver='new'),
            ])
            svc_ids = [
                MapConfigId(ItemType.CONTAINER, self.map_name, 'server3'),
                MapConfigId(ItemType.CONTAINER, self.map_name, 'net_svc')
            ]
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(svc_ids))
            self.assertEqual(states['containers'][('net_svc', None)].state_flags & StateFlags.NETWORK_DISCONNECTED, StateFlags.NETWORK_DISCONNECTED)
            self.assertEqual(states['containers'][('server3', None)].state_flags & StateFlags.NETWORK_DISCONNECTED, StateFlags.NETWORK_DISCONNECTED)
            self.assertEqual(states['networks']['app_net1'].base_state, State.ABSENT)
            self.assertEqual(states['networks']['app_net2'].state_flags & StateFlags.MISC_MISMATCH, StateFlags.MISC_MISMATCH)

    def test_update_states_network_mismatch(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('net_svc', network_link_valid=False),
                _container('server3', network_ep_valid=False),
            ], [
                _network('app_net1'),
                _network('app_net2'),
            ])
            svc_ids = [
                MapConfigId(ItemType.CONTAINER, self.map_name, 'server3'),
                MapConfigId(ItemType.CONTAINER, self.map_name, 'net_svc')
            ]
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(svc_ids))
            self.assertEqual(states['containers'][('net_svc', None)].state_flags & StateFlags.NETWORK_MISMATCH, StateFlags.NETWORK_MISMATCH)
            self.assertEqual(states['containers'][('server3', None)].state_flags & StateFlags.NETWORK_MISMATCH, StateFlags.NETWORK_MISMATCH)

    def test_update_states_left_network(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('server3', extra_network=True),
            ], [
                _network('app_net1'),
                _network('app_net2'),
            ])
            svc_ids = [
                MapConfigId(ItemType.CONTAINER, self.map_name, 'server3'),
            ]
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(svc_ids))
            self.assertEqual(states['containers'][('server3', None)].state_flags & StateFlags.NETWORK_LEFT, StateFlags.NETWORK_LEFT)

    def test_update_states_updated_environment(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_default_containers(rsps)
            self.sample_map.containers['server'].create_options.update(environment=dict(Test='x'))
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.MISC_MISMATCH, StateFlags.MISC_MISMATCH)

    def test_update_states_updated_command(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_default_containers(rsps)
            self.sample_map.containers['server'].create_options.update(command='/bin/true')
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.MISC_MISMATCH, StateFlags.MISC_MISMATCH)

    def test_update_states_updated_exec(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            cmd1 = ExecCommand(2, '/bin/true', ExecPolicy.INITIAL)
            cmd2 = ExecCommand(3, '/bin/true', ExecPolicy.INITIAL)
            cmd3 = ExecCommand(4, '/bin/true', ExecPolicy.RESTART)
            self.sample_map.containers['server'].exec_commands = [cmd1]
            self._setup_default_containers(rsps)
            self.sample_map.containers['server'].exec_commands = [cmd1, cmd2, cmd3]
            states = _get_states_dict(UpdateStateGenerator(self.policy, {}).get_states(self.server_config_id))
            server_state = states['containers'][('server', None)]
            self.assertEqual(server_state.base_state, State.RUNNING)
            self.assertEqual(server_state.state_flags & StateFlags.NEEDS_RESET, 0)
            self.assertEqual(server_state.state_flags & StateFlags.EXEC_COMMANDS, StateFlags.EXEC_COMMANDS)
            self.assertDictEqual(server_state.extra_data, {
                'exec_commands': [cmd3],
                'id': get_container_id('{0}.server'.format(self.map_name, 'server')),
                'pid': 1,
            })


class TestPolicyStateUtils(unittest.TestCase):
    def setUp(self):
        self.map_name = map_name = 'main'
        self.sample_map = sample_map = ContainerMap('main', MAP_DATA_2,
                                                    use_attached_parent_name=True).get_extended_map()
        self.sample_client_config = client_config = ClientConfiguration(**CLIENT_DATA_1)
        self.policy = policy = BasePolicy({map_name: sample_map}, {'__default__': client_config})
        self.state_gen = DependencyStateGenerator(policy, {})
        self.server_dependencies = [
            (ItemType.IMAGE, map_name, 'registry.example.com/sub_sub_svc', 'latest'),
            (ItemType.CONTAINER, map_name, 'sub_sub_svc', None),
            (ItemType.IMAGE, map_name, 'registry.example.com/sub_svc', 'latest'),
            (ItemType.CONTAINER, map_name, 'sub_svc', None),
            (ItemType.VOLUME, map_name, 'redis', 'redis_socket'),
            (ItemType.VOLUME, map_name, 'redis', 'redis_log'),
            (ItemType.IMAGE, map_name, 'registry.example.com/redis', 'latest'),
            (ItemType.IMAGE, map_name, 'registry.example.com/svc', 'latest'),
            (ItemType.CONTAINER, map_name, 'redis', 'queue'),
            (ItemType.CONTAINER, map_name, 'redis', 'cache'),
            (ItemType.CONTAINER, map_name, 'svc', None),
            (ItemType.VOLUME, map_name, 'server', 'app_log'),
            (ItemType.VOLUME, map_name, 'server', 'server_log'),
            (ItemType.IMAGE, map_name, 'registry.example.com/server', 'latest'),
        ]
        self.redis_dependencies = [
            (ItemType.IMAGE, map_name, 'registry.example.com/sub_sub_svc', 'latest'),
            (ItemType.CONTAINER, self.map_name, 'sub_sub_svc', None),
            (ItemType.IMAGE, map_name, 'registry.example.com/sub_svc', 'latest'),
            (ItemType.CONTAINER, self.map_name, 'sub_svc', None),
            (ItemType.VOLUME, map_name, 'redis', 'redis_socket'),
            (ItemType.VOLUME, map_name, 'redis', 'redis_log'),
            (ItemType.IMAGE, map_name, 'registry.example.com/redis', 'latest'),
        ]

    def test_merge_single(self):
        redis_config = self._config_id('redis', 'queue')
        merged_paths = merge_dependency_paths([
            (redis_config, self.state_gen.get_dependency_path(redis_config))
        ])
        self.assertItemsEqual([
            (redis_config, self.redis_dependencies)
        ], merged_paths)

    def test_merge_empty(self):
        svc_config = self._config_id('sub_sub_svc')
        merged_paths = merge_dependency_paths([
            (svc_config, [])
        ])
        self.assertItemsEqual([(svc_config, [])], merged_paths)

    def _config_id(self, config_name, instance=None):
        return MapConfigId(ItemType.CONTAINER, self.map_name, config_name, instance)

    def test_merge_two_common(self):
        server_config = self._config_id('server')
        worker_config = self._config_id('worker')
        merged_paths = merge_dependency_paths([
            (c, self.state_gen.get_dependency_path(c))
            for c in [server_config, worker_config]
        ])
        self.assertEqual(len(merged_paths), 2)
        self.assertEqual(merged_paths[0][0], server_config)
        self.assertListEqual(self.server_dependencies, merged_paths[0][1])
        self.assertEqual(merged_paths[1][0], worker_config)
        self.assertListEqual([
            (ItemType.VOLUME, self.map_name, 'worker', 'app_log'),
        ], merged_paths[1][1])

    def test_merge_three_common(self):
        server_config = self._config_id('server')
        worker_config = self._config_id('worker')
        worker_q2_config = self._config_id('worker_q2')
        merged_paths = merge_dependency_paths([
            (c, self.state_gen.get_dependency_path(c))
            for c in [server_config, worker_config, worker_q2_config]
        ])
        self.assertEqual(len(merged_paths), 3)
        self.assertEqual(merged_paths[0][0], server_config)
        self.assertEqual(merged_paths[1][0], worker_config)
        self.assertEqual(merged_paths[2][0], worker_q2_config)
        self.assertListEqual(self.server_dependencies, merged_paths[0][1])
        self.assertListEqual([
            (ItemType.VOLUME, self.map_name, 'worker', 'app_log'),
        ], merged_paths[1][1])
        self.assertListEqual([
            (ItemType.VOLUME, self.map_name, 'worker_q2', 'app_log'),
        ], merged_paths[2][1])

    def test_merge_three_common_with_extension(self):
        worker_config = self._config_id('worker')
        server2_config = self._config_id('server2')
        worker_q2_config = self._config_id('worker_q2')
        merged_paths = merge_dependency_paths([
            (c, self.state_gen.get_dependency_path(c))
            for c in [worker_config, server2_config, worker_q2_config]
        ])
        self.assertEqual(len(merged_paths), 3)
        self.assertEqual(merged_paths[0][0], worker_config)
        self.assertEqual(merged_paths[1][0], server2_config)
        self.assertEqual(merged_paths[2][0], worker_q2_config)
        self.assertListEqual([
            (ItemType.IMAGE, self.map_name, 'registry.example.com/sub_sub_svc', 'latest'),
            (ItemType.CONTAINER, self.map_name, 'sub_sub_svc', None),
            (ItemType.IMAGE, self.map_name, 'registry.example.com/sub_svc', 'latest'),
            (ItemType.CONTAINER, self.map_name, 'sub_svc', None),
            (ItemType.VOLUME, self.map_name, 'redis', 'redis_socket'),
            (ItemType.VOLUME, self.map_name, 'redis', 'redis_log'),
            (ItemType.IMAGE, self.map_name, 'registry.example.com/redis', 'latest'),
            (ItemType.IMAGE, self.map_name, 'registry.example.com/svc', 'latest'),
            (ItemType.CONTAINER, self.map_name, 'redis', 'queue'),
            (ItemType.CONTAINER, self.map_name, 'redis', 'cache'),
            (ItemType.CONTAINER, self.map_name, 'svc', None),
            (ItemType.VOLUME, self.map_name, 'worker', 'app_log'),
            (ItemType.IMAGE, self.map_name, 'registry.example.com/server', 'latest'),
        ], merged_paths[0][1])
        self.assertListEqual([
            (ItemType.IMAGE, self.map_name, 'registry.example.com/svc2', 'latest'),
            (ItemType.CONTAINER, self.map_name, 'svc2', None),
            (ItemType.VOLUME, self.map_name, 'server2', 'app_log'),
            (ItemType.VOLUME, self.map_name, 'server2', 'server_log'),
        ], merged_paths[1][1])
        self.assertListEqual([
            (ItemType.VOLUME, self.map_name, 'worker_q2', 'app_log'),
        ], merged_paths[2][1])

    def test_merge_included_first(self):
        redis_config = self._config_id('redis', 'cache')
        server_config = self._config_id('server')
        merged_paths = merge_dependency_paths([
            (c, self.state_gen.get_dependency_path(c))
            for c in [redis_config, server_config]
        ])
        self.assertEqual(len(merged_paths), 1)
        self.assertEqual(merged_paths[0][0], server_config)
        self.assertListEqual(self.server_dependencies, merged_paths[0][1])

    def test_merge_included_second(self):
        server_config = self._config_id('server')
        redis_config = self._config_id('redis', 'cache')
        merged_paths = merge_dependency_paths([
            (c, self.state_gen.get_dependency_path(c))
            for c in [server_config, redis_config]
        ])
        self.assertEqual(len(merged_paths), 1)
        self.assertEqual(merged_paths[0][0], server_config)
        self.assertListEqual(self.server_dependencies, merged_paths[0][1])

    def test_merge_included_multiple(self):
        sub_svc_config = self._config_id('sub_svc')
        sub_sub_svc_config = self._config_id('sub_sub_svc')
        svc_config = self._config_id('svc')
        server_config = self._config_id('server')
        redis_config = self._config_id('redis', 'queue')
        server2_config = self._config_id('server2')
        merged_paths = merge_dependency_paths([
            (c, self.state_gen.get_dependency_path(c))
            for c in [sub_sub_svc_config, sub_svc_config, svc_config, server_config, redis_config, server2_config]
        ])
        self.assertEqual(len(merged_paths), 2)
        self.assertEqual(merged_paths[0][0], server_config)
        self.assertEqual(merged_paths[1][0], server2_config)
        self.assertListEqual(self.server_dependencies, merged_paths[0][1])
        self.assertListEqual([
            (ItemType.IMAGE, self.map_name, 'registry.example.com/svc2', 'latest'),
            (ItemType.CONTAINER, self.map_name, 'svc2', None),
            (ItemType.VOLUME, self.map_name, 'server2', 'app_log'),
            (ItemType.VOLUME, self.map_name, 'server2', 'server_log'),
        ], merged_paths[1][1])
