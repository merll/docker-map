# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from collections import defaultdict

import posixpath
import unittest
import responses

from dockermap import DEFAULT_COREIMAGE, DEFAULT_BASEIMAGE
from dockermap.map.config import ClientConfiguration, get_host_path
from dockermap.map.container import ContainerMap
from dockermap.map.input import ExecCommand, EXEC_POLICY_INITIAL, EXEC_POLICY_RESTART
from dockermap.map.policy import CONFIG_FLAG_DEPENDENT
from dockermap.map.policy.base import BasePolicy
from dockermap.map.state import (INITIAL_START_TIME, STATE_RUNNING, STATE_PRESENT, STATE_ABSENT,
                                 STATE_FLAG_NONRECOVERABLE, STATE_FLAG_RESTARTING, STATE_FLAG_INITIAL,
                                 STATE_FLAG_OUTDATED)
from dockermap.map.state.base import DependencyStateGenerator, DependentStateGenerator, SingleStateGenerator
from dockermap.map.state.update import UpdateStateGenerator

from tests import MAP_DATA_2, CLIENT_DATA_1


URL_PREFIX = 'http+docker://localunixsocket/v{0}'.format(CLIENT_DATA_1['version'])

P_STATE_INITIAL = 0
P_STATE_RUNNING = 1
P_STATE_RESTARTING = 2
P_STATE_EXITED_0 = 3
P_STATE_EXITED_127 = 4
STATE_RESULTS = {
    P_STATE_INITIAL: {
        'Running': False,
        'Restarting': False,
        'ExitCode': 0,
        'StartedAt': INITIAL_START_TIME,
    },
    P_STATE_RESTARTING: {
        'Running': False,
        'Restarting': True,
        'ExitCode': 255,
        'StartedAt': "2016-02-05T20:14:04.655843958Z",
    },
    P_STATE_RUNNING: {
        'Running': True,
        'Restarting': False,
        'ExitCode': 0,
        'StartedAt': "2016-02-05T20:14:04.655843958Z",
    },
    P_STATE_EXITED_0: {
        'Running': False,
        'Restarting': False,
        'ExitCode': 0,
        'StartedAt': "2016-02-05T20:14:04.655843958Z",
    },
    P_STATE_EXITED_127: {
        'Running': False,
        'Restarting': False,
        'ExitCode': -127,
        'StartedAt': "2016-02-05T20:14:04.655843958Z",
    },
}


def _container(config_name, p_state=P_STATE_RUNNING, instances=None, attached_volumes_valid=True,
               instance_volumes_valid=True, **kwargs):
    return config_name, p_state, instances, attached_volumes_valid, instance_volumes_valid, kwargs


def _add_container_list(rsps, container_names):
    results = [
        {'Id': '{0}'.format(c_id), 'Names': ['/{0}'.format(name)]}
        for c_id, name in container_names
    ]
    rsps.add('GET', '{0}/containers/json'.format(URL_PREFIX), content_type='application/json', json=results)


def _add_image_list(rsps, image_names):
    image_list = [
        {
            'RepoTags': ['{0}:latest'.format(i_name), '{0}:1.0'.format(i_name)] if ':' not in i_name else [i_name],
            'Id': '{0}'.format(i_id),
        }
        for i_id, i_name in image_names
    ]
    rsps.add('GET', '{0}/images/json'.format(URL_PREFIX), content_type='application/json', json=image_list)
    rsps.add('POST', '{0}/images/create'.format(URL_PREFIX), content_type='application/json')


def _get_container_mounts(container_map, c_config, config_name, instance_name, valid, is_attached=False):
    if valid:
        path_prefix = '/valid'
    else:
        path_prefix = '/invalid_{0}'.format(config_name)
    for a in c_config.attaches:
        c_path = container_map.volumes[a]
        yield {'Source': posixpath.join(path_prefix, 'attached', a), 'Destination': c_path, 'RW': True}
    if not is_attached:
        for vol, ro in c_config.binds:
            if isinstance(vol, tuple):
                c_path, h_r_path = vol
                h_path = get_host_path(container_map.host.root, h_r_path, instance_name)
            else:
                c_path = container_map.volumes[vol]
                h_path = container_map.host.get_path(vol, instance_name)
            yield {'Source': posixpath.join(path_prefix, h_path), 'Destination': c_path, 'RW': not ro}
        for s in c_config.shares:
            yield {'Source': posixpath.join(path_prefix, 'shared', s), 'Destination': s, 'RW': True}
        for vol, ro in c_config.uses:
            c, __, i = vol.partition('.')
            c_ref = container_map.get_existing(c)
            if i in c_ref.attaches:
                c_path = container_map.volumes[i]
                yield {'Source': posixpath.join(path_prefix, 'attached', i), 'Destination': c_path, 'RW': not ro}
            elif c_ref and (not i or i in c_ref.instances):
                for r_mount in _get_container_mounts(container_map, c_ref, c, i, valid):
                    yield r_mount
            else:
                raise ValueError("Invalid uses declaration in {0}: {1}".format(config_name, vol))


def _add_inspect(rsps, container_map, map_name, c_config, config_name, instance_name, state, valid, container_id,
                 image_id, is_attached, **kwargs):
    if instance_name:
        container_name = '{0}.{1}.{2}'.format(map_name, config_name, instance_name)
    else:
        container_name = '{0}.{1}'.format(map_name, config_name)
    ports = defaultdict(list)
    if not is_attached:
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
    results = {
        'Id': '{0}'.format(container_id),
        'Names': ['/{0}'.format(container_name)],
        'State': STATE_RESULTS[state],
        'Image': '{0}'.format(image_id),
        'Mounts': list(_get_container_mounts(container_map, c_config, config_name, instance_name, valid, is_attached)),
        'HostConfig': {'Links': [
            '/{0}.{1}:/{2}/{3}'.format(map_name, link.container, container_name, link.alias)
            for link in c_config.links
        ]},
        'Config': {
            'Env': None,
            'Cmd': [],
            'Entrypoint': [],
        },
        'NetworkSettings': {
            'Ports': ports,
        },
    }
    exec_results = {
        'Processes': [
            [cmd_i, cmd.user, cmd.cmd]
            for cmd_i, cmd in enumerate(c_config.exec_commands)
        ],
    }
    results.update(kwargs)
    rsps.add('GET', '{0}/containers/{1}/json'.format(URL_PREFIX, container_name),
             content_type='application/json',
             json=results)
    rsps.add('GET', '{0}/containers/{1}/json'.format(URL_PREFIX, container_id),
             content_type='application/json',
             json=results)
    rsps.add('GET', '{0}/containers/{1}/top'.format(URL_PREFIX, container_name),
             content_type='application/json',
             json=exec_results)
    rsps.add('GET', '{0}/containers/{1}/top'.format(URL_PREFIX, container_id),
             content_type='application/json',
             json=exec_results)
    return container_id, container_name


def _get_single_state(sg, map_name, config_name, instance=None):
    if instance:
        instances = [instance]
    else:
        instances = None
    states = [si
              for s in sg.get_states(map_name, config_name, instances)
              for si in s.instances]
    return states[0]


class TestPolicyStateGenerators(unittest.TestCase):
    def setUp(self):
        self.map_name = map_name = 'main'
        self.sample_map = sample_map = ContainerMap('main', MAP_DATA_2,
                                                    use_attached_parent_name=True).get_extended_map()
        self.sample_map.repository = None
        self.sample_client_config = client_config = ClientConfiguration(**CLIENT_DATA_1)
        self.policy = BasePolicy({map_name: sample_map}, {'__default__': client_config})
        all_images = set(c_config.image or c_name for c_name, c_config in sample_map)
        all_images.add(DEFAULT_COREIMAGE)
        all_images.add(DEFAULT_BASEIMAGE)
        self.images = list(enumerate(all_images))

    def _setup_containers(self, rsps, containers_states):
        container_names = []
        _add_image_list(rsps, self.images)
        image_dict = {name: _id for _id, name in self.images}
        container_id = 0
        base_image_id = image_dict[DEFAULT_BASEIMAGE]
        for name, state, instances, attached_valid, instances_valid, kwargs in containers_states:
            c_config = self.sample_map.get_existing(name)
            for a in c_config.attaches:
                container_id += 1
                container_names.append(_add_inspect(rsps, self.sample_map, self.map_name, c_config, name, a,
                                                    P_STATE_EXITED_0, attached_valid, container_id, base_image_id,
                                                    True))
            image_id = image_dict[c_config.image or name]
            for i in instances or c_config.instances or [None]:
                container_id += 1
                container_names.append(_add_inspect(rsps, self.sample_map, self.map_name, c_config, name, i,
                                                    state, instances_valid, container_id, image_id, False, **kwargs))
        _add_container_list(rsps, container_names)

    def test_dependency_states_running(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis'),
                _container('svc'),
                _container('server'),
            ])
            states = list(DependencyStateGenerator(self.policy, {}).get_states(self.map_name, 'server'))
            instance_base_states = [si.base_state
                                    for s in states
                                    for si in s.instances]
            attached_base_states = [si.base_state
                                    for s in states
                                    for si in s.attached]
            self.assertTrue(all(si == STATE_RUNNING
                                for si in instance_base_states))
            self.assertTrue(all(si == STATE_PRESENT
                                for si in attached_base_states))
            self.assertTrue(all(s.flags == CONFIG_FLAG_DEPENDENT
                                for s in states
                                if s.config != 'server'))

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
            cache_state = _get_single_state(sg, self.map_name, 'redis', 'cache')
            self.assertEqual(cache_state.base_state, STATE_PRESENT)
            queue_state = _get_single_state(sg, self.map_name, 'redis', 'queue')
            self.assertEqual(queue_state.base_state, STATE_RUNNING)
            svc_state = _get_single_state(sg, self.map_name, 'svc')
            self.assertEqual(svc_state.base_state, STATE_PRESENT)
            self.assertEqual(svc_state.flags & STATE_FLAG_NONRECOVERABLE, STATE_FLAG_NONRECOVERABLE)
            worker_state = _get_single_state(sg, self.map_name, 'worker')
            self.assertEqual(worker_state.flags & STATE_FLAG_RESTARTING, STATE_FLAG_RESTARTING)
            worker2_state = _get_single_state(sg, self.map_name, 'worker_q2')
            self.assertEqual(worker2_state.base_state, STATE_PRESENT)
            self.assertEqual(worker2_state.flags & STATE_FLAG_INITIAL, STATE_FLAG_INITIAL)
            server_states = _get_single_state(sg, self.map_name, 'server')
            self.assertEqual(server_states.base_state, STATE_ABSENT)

    def test_dependent_states(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis'),
                _container('server'),
                _container('worker'),
                _container('worker_q2'),
            ])
            states = list(DependentStateGenerator(self.policy, {}).get_states(self.map_name, 'redis'))
            instance_base_states = [si.base_state
                                    for s in states
                                    for si in s.instances]
            attached_base_states = [si.base_state
                                    for s in states
                                    for si in s.attached]
            self.assertTrue(all(si == STATE_RUNNING
                                for si in instance_base_states))
            self.assertTrue(all(si == STATE_PRESENT
                                for si in attached_base_states))
            self.assertTrue(all(s.flags == CONFIG_FLAG_DEPENDENT
                                for s in states
                                if s.config != 'redis'))

    def test_update_states_clean(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis'),
                _container('svc'),
                _container('server'),
            ])
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags, 0)
            redis_states = states['redis'].instances[0]
            self.assertEqual(redis_states.base_state, STATE_RUNNING)
            self.assertEqual(redis_states.flags, 0)

    def test_update_states_invalid_attached(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis', attached_volumes_valid=False),
                _container('svc'),
                _container('server'),
            ])
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags & STATE_FLAG_OUTDATED, STATE_FLAG_OUTDATED)
            redis_states = states['redis'].instances[0]
            self.assertEqual(redis_states.base_state, STATE_RUNNING)
            self.assertEqual(redis_states.flags & STATE_FLAG_OUTDATED, STATE_FLAG_OUTDATED)

    def test_update_states_invalid_dependent_instance(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis', instance_volumes_valid=False),
                _container('svc'),
                _container('server'),
            ])
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags & STATE_FLAG_OUTDATED, 0)
            redis_states = states['redis'].instances[0]
            self.assertEqual(redis_states.base_state, STATE_RUNNING)
            self.assertEqual(redis_states.flags & STATE_FLAG_OUTDATED, STATE_FLAG_OUTDATED)

    def test_update_states_invalid_dependent_instance_attached(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis'),
                _container('svc'),
                _container('server', attached_volumes_valid=False),
            ])
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags & STATE_FLAG_OUTDATED, STATE_FLAG_OUTDATED)
            redis_states = states['redis'].instances[0]
            self.assertEqual(redis_states.base_state, STATE_RUNNING)
            self.assertEqual(redis_states.flags & STATE_FLAG_OUTDATED, 0)

    def test_update_states_invalid_image(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis'),
                _container('svc'),
                _container('server', Image='invalid'),
            ])
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags & STATE_FLAG_OUTDATED, STATE_FLAG_OUTDATED)

    def test_update_states_invalid_network(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis'),
                _container('svc'),
                _container('server', NetworkSettings=dict(Ports={})),
            ])
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags & STATE_FLAG_OUTDATED, STATE_FLAG_OUTDATED)

    def test_update_states_updated_environment(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis'),
                _container('svc'),
                _container('server'),
            ])
            self.sample_map.containers['server'].create_options.update(environment=dict(Test='x'))
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags & STATE_FLAG_OUTDATED, STATE_FLAG_OUTDATED)

    def test_update_states_updated_command(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            self._setup_containers(rsps, [
                _container('redis'),
                _container('svc'),
                _container('server'),
            ])
            self.sample_map.containers['server'].create_options.update(command='/bin/true')
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags & STATE_FLAG_OUTDATED, STATE_FLAG_OUTDATED)

    def test_update_states_updated_exec(self):
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            cmd1 = ExecCommand(2, '/bin/true', EXEC_POLICY_INITIAL)
            cmd2 = ExecCommand(3, '/bin/true', EXEC_POLICY_INITIAL)
            cmd3 = ExecCommand(4, '/bin/true', EXEC_POLICY_RESTART)
            self.sample_map.containers['server'].exec_commands = [cmd1]
            self._setup_containers(rsps, [
                _container('redis'),
                _container('svc'),
                _container('server'),
            ])
            self.sample_map.containers['server'].exec_commands = [cmd1, cmd2, cmd3]
            states = {s.config: s for s in UpdateStateGenerator(self.policy, {}).get_states(self.map_name, 'server')}
            server_states = states['server'].instances[0]
            self.assertEqual(server_states.base_state, STATE_RUNNING)
            self.assertEqual(server_states.flags & STATE_FLAG_OUTDATED, 0)
            self.assertDictEqual(server_states.extra_data, {'exec_commands': [
                (cmd1, True),
                (cmd2, False),
                (cmd3, False),
            ]})
