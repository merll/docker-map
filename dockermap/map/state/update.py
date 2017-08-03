# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import defaultdict
import logging
import shlex
import six

from ...functional import resolve_value
from ..input import ExecPolicy, NetworkEndpoint
from ..policy import ConfigFlags
from ..policy.utils import init_options, get_shared_volume_path, get_instance_volumes, extract_user
from . import State, StateFlags, SimpleEnum
from .base import DependencyStateGenerator, ContainerBaseState, NetworkBaseState

log = logging.getLogger(__name__)


class CmdCheck(SimpleEnum):
    FULL = 'full'
    PARTIAL = 'partial'
    NONE = 'none'

# For backwards compatibility.
CMD_CHECK_FULL = CmdCheck.FULL
CMD_CHECK_PARTIAL = CmdCheck.PARTIAL
CMD_CHECK_NONE = CmdCheck.NONE


def _check_environment(c_config, instance_detail):
    def _parse_env():
        for env_str in instance_env:
            var_name, sep, env_val = env_str.partition('=')
            if sep:
                yield var_name, env_val

    create_options = init_options(c_config.create_options)
    if not create_options:
        return True
    instance_env = instance_detail['Config']['Env'] or []
    config_env = resolve_value(create_options.get('environment'))
    if not config_env:
        return True
    current_env = dict(_parse_env())
    log.debug("Checking environment. Config / container instance:\n%s\n%s", config_env, current_env)
    for k, v in six.iteritems(config_env):
        if current_env.get(k) != resolve_value(v):
            return False
    return True


def _strip_quotes(cmd_item):
    if len(cmd_item) >= 2:
        first, last = cmd_item[0], cmd_item[-1]
        if first in ("'", '"') and first == last:
            return cmd_item[1:-1]
    return cmd_item


def _normalize_cmd(cmd):
    if isinstance(cmd, six.string_types):
        cmd = shlex.split(cmd)
    return list(map(_strip_quotes, cmd))


def _check_cmd(c_config, instance_detail):
    create_options = init_options(c_config.create_options)
    if not create_options:
        return True
    instance_config = instance_detail['Config']
    config_cmd = resolve_value(create_options.get('command')) if create_options else None
    if config_cmd:
        instance_cmd = instance_config['Cmd'] or []
        log.debug("Checking command. Config / container instance:\n%s\n%s", config_cmd, instance_cmd)
        if _normalize_cmd(config_cmd) != instance_cmd:
            return False
    config_entrypoint = resolve_value(create_options.get('entrypoint')) if create_options else None
    if config_entrypoint:
        instance_entrypoint = instance_config['Entrypoint'] or []
        log.debug("Checking entrypoint. Config / container instance:\n%s\n%s", config_entrypoint, instance_entrypoint)
        if isinstance(config_entrypoint, six.string_types):
            if [config_entrypoint] != instance_entrypoint:
                return False
        elif list(config_entrypoint) != instance_entrypoint:
            return False
    return True


def _check_container_network_ports(container_config, client_config, instance_detail):
    if not container_config.exposes:
        return True
    instance_ports = instance_detail['NetworkSettings']['Ports'] or {}
    for port_binding in container_config.exposes:
        port = resolve_value(port_binding.exposed_port)
        i_key = port if isinstance(port, six.string_types) and '/' in port else '{0}/tcp'.format(port)
        log.debug("Looking up port %s configuration.", i_key)
        if i_key not in instance_ports:
            log.debug("Not found.")
            return False
        bind_port = resolve_value(port_binding.host_port)
        if bind_port:
            i_val = instance_ports[i_key]
            if not i_val:
                log.debug("Port is exposed but not published.")
                return False
            interface = resolve_value(port_binding.interface)
            if interface:
                bind_addr = resolve_value(client_config.interfaces.get(interface))
            else:
                bind_addr = '0.0.0.0'
            bind_config = {'HostIp': bind_addr, 'HostPort': six.text_type(bind_port)}
            log.debug("Checking port. Config / container instance:\n%s\n%s", bind_config, i_val)
            if bind_config not in i_val:
                return False
    return True


def _check_network_driver_opts(network_config, instance_detail):
    driver_opts = init_options(network_config.driver_options)
    if not driver_opts:
        return True
    opts = {option_key: option_value
            for option_key, option_value in six.iteritems(instance_detail['Options'])}
    for c_key, c_val in six.iteritems(driver_opts):
        if resolve_value(c_val) != opts.get(c_key):
            return False
    return True


class SingleContainerVfsCheck(object):
    """
    :type vfs_paths: dict[tuple, unicode | str]
    :type config_id: dockermap.map.input.MapConfigId
    :type container_map: dockermap.map.config.main.ContainerMap
    :type instance_volumes: dict[unicode | str, unicode | str]
    """
    def __init__(self, vfs_paths, config_id, container_map, instance_volumes):
        self._vfs_paths = vfs_paths
        self._instance_volumes = instance_volumes
        self._config_id = config_id
        self._container_map = container_map
        self._use_parent_name = container_map.use_attached_parent_name
        self._volumes = container_map.volumes

    def check_bind(self, config, instance):
        config_id = self._config_id
        for shared_volume in config.binds:
            bind_path, host_path = get_shared_volume_path(self._container_map, shared_volume.volume, instance)
            instance_vfs = self._instance_volumes.get(bind_path)
            log.debug("Checking host bind. Config / container instance:\n%s\n%s", host_path, instance_vfs)
            if not (instance_vfs and host_path == instance_vfs):
                return False
            self._vfs_paths[config_id.config_name, config_id.instance_name, bind_path] = instance_vfs
        return True

    def check_attached(self, config, parent_name):
        config_id = self._config_id
        for attached in config.attaches:
            a_name = '{0}.{1}'.format(parent_name, attached) if self._use_parent_name else attached
            attached_path = resolve_value(self._volumes[attached])
            instance_vfs = self._instance_volumes.get(attached_path)
            attached_vfs = self._vfs_paths.get((a_name, None, attached_path))
            log.debug("Checking attached %s path. Attached instance / dependent container instance:\n%s\n%s",
                      attached, attached_vfs, instance_vfs)
            if not (instance_vfs and attached_vfs == instance_vfs):
                return False
            self._vfs_paths[config_id.config_name, config_id.instance_name, attached_path] = instance_vfs
        return True

    def check_used(self, config):
        config_id = self._config_id
        for used in config.uses:
            used_volume = used.volume
            if self._use_parent_name:
                used_alias = used_volume.partition('.')[2]
            else:
                used_alias = used_volume
            used_path = resolve_value(self._volumes.get(used_alias))
            if used_path:
                used_vfs = self._vfs_paths.get((used_volume, None, used_path))
                instance_path = self._instance_volumes.get(used_path)
                log.debug("Checking used %s path. Parent instance / dependent container instance:\n%s\n%s",
                          used_volume, used_vfs, instance_path)
                if used_vfs != instance_path:
                    return False
                continue
            ref_c_name, __, ref_i_name = used_volume.partition('.')
            log.debug("Looking up dependency %s (instance %s).", ref_c_name, ref_i_name)
            ref_config = self._container_map.get_existing(ref_c_name)
            if ref_config:
                for share in ref_config.shares:
                    ref_shared_path = resolve_value(share)
                    i_shared_path = self._instance_volumes.get(ref_shared_path)
                    shared_vfs = self._vfs_paths.get((ref_c_name, ref_i_name, ref_shared_path))
                    log.debug("Checking shared path %s. Parent instance / dependent container instance:\n%s\n%s",
                              share, shared_vfs, i_shared_path)
                    if shared_vfs != i_shared_path:
                        return False
                    self._vfs_paths[(config_id.config_name, config_id.instance_name, ref_shared_path)] = i_shared_path
                self.check_bind(ref_config, ref_i_name)
                self.check_attached(ref_config, ref_c_name)
            else:
                raise ValueError("Volume alias or container reference could not be resolved: {0}".format(used))
        return True


class ContainerVolumeChecker(object):
    def __init__(self):
        self._vfs_paths = {}

    def register_attached(self, mapped_path, path, alias, parent_name=None):
        alias = '{0}.{1}'.format(parent_name, alias) if parent_name else alias
        self._vfs_paths[alias, None, mapped_path] = path

    def check(self, config_id, container_map, container_config, instance_detail):
        instance_volumes = get_instance_volumes(instance_detail)
        vfs = SingleContainerVfsCheck(self._vfs_paths, config_id, container_map, instance_volumes)
        for share in container_config.shares:
            cr_shared_path = resolve_value(share)
            self._vfs_paths[config_id.config_name, config_id.instance_name, cr_shared_path] = instance_volumes.get(share)
        if not vfs.check_bind(container_config, config_id.instance_name):
            return False
        if not vfs.check_attached(container_config, config_id.config_name):
            return False
        if not vfs.check_used(container_config):
            return False
        return True


class NetworkEndpointRegistry(object):
    def __init__(self, nname_func, cname_func, hostname_func, default_networks):
        self._nname = nname_func
        self._cname = cname_func
        self._hostname = hostname_func
        self._default_networks = list(default_networks.keys())
        self._endpoints = defaultdict(set)
        for network_detail in six.itervalues(default_networks):
            self.register_network(network_detail)

    def register_network(self, detail):
        network_id = detail['Id']
        for c_id, c_detail in six.iteritems(detail.get('Containers') or {}):
            self._endpoints[c_id].add((network_id, c_detail['EndpointID']))

    def check_container_config(self, config_id, c_config, detail):
        if not detail['Config'].get('NetworkDisabled', False):
            i_networks = detail['NetworkSettings'].get('Networks', {})
            connected_network_names = set(i_networks.keys())
        else:
            i_networks = {}
            connected_network_names = set()
        c_net_mode = c_config.network_mode or 'default'
        if c_config.networks:
            named_endpoints = [(self._nname(config_id.map_name, cn_config.network_name), cn_config)
                               for cn_config in c_config.networks]
        elif c_net_mode in ('default', 'bridge'):
            named_endpoints = [(d_name, NetworkEndpoint(d_name))
                               for d_name in self._default_networks]
        elif c_net_mode == 'none':
            named_endpoints = []
        else:
            if isinstance(c_net_mode, tuple):
                cn_name = 'container:{0}'.format(self._cname(config_id.map_name, *c_net_mode))
            else:
                cn_name = c_net_mode
            if cn_name not in connected_network_names:
                log.debug("Configurations network mode %s not set in available connections: %s.", cn_name,
                          connected_network_names)
                return (StateFlags.NETWORK_LEFT | StateFlags.NETWORK_DISCONNECTED), {
                    'left': connected_network_names,
                    'disconnected': [NetworkEndpoint(cn_name)]
                }
            return StateFlags.NONE, {}
        disconnected_networks = []
        configured_network_names = {ce[0] for ce in named_endpoints}
        network_endpoints = self._endpoints.get(detail['Id'], set())
        reset_networks = []
        for ref_n_name, cn_config in named_endpoints:
            log.debug("Checking network %s.", ref_n_name)
            if ref_n_name not in connected_network_names:
                log.debug("Network %s not found in container connections.", ref_n_name)
                disconnected_networks.append(cn_config)
                continue
            network_detail = i_networks[ref_n_name]
            c_alias_set = set(cn_config.aliases or ())
            if c_alias_set and not c_alias_set.issubset(network_detail.get('Aliases')):
                log.debug("Aliases in network %s differ or are not present.", ref_n_name)
                reset_networks.append((ref_n_name, cn_config))
                continue
            if (network_detail['NetworkID'], network_detail['EndpointID']) not in network_endpoints:
                log.debug("Network endpoint not found in %s (%s): %s", ref_n_name, network_detail['NetworkID'],
                          network_detail['EndpointID'])
                reset_networks.append((ref_n_name, cn_config))
                continue
            if cn_config.links:
                linked_names = {'{0}:{1}'.format(self._cname(config_id.map_name, lc_name),
                                                 lc_alias or self._hostname(lc_name))
                                for lc_name, lc_alias in cn_config.links}
            else:
                linked_names = set()
            if set(network_detail.get('Links', []) or ()) != linked_names:
                log.debug("Links in %s differ from configuration: %s.", ref_n_name, network_detail.get('Links', []))
                reset_networks.append((ref_n_name, cn_config))
                continue
        s_flags = StateFlags.NONE
        extra = {}
        if disconnected_networks:
            log.debug("Container is not connected to configured networks: %s.", disconnected_networks)
            s_flags |= StateFlags.NETWORK_DISCONNECTED
            extra['disconnected'] = disconnected_networks
        if reset_networks:
            log.debug("Container is connected, but with different settings from the configuration: %s.", reset_networks)
            s_flags |= StateFlags.NETWORK_MISMATCH
            extra['reconnect'] = reset_networks
        left_networks = connected_network_names - configured_network_names
        if left_networks:
            log.debug("Container is connected to the following networks that it is not configured for: %s.",
                      left_networks)
            s_flags |= StateFlags.NETWORK_LEFT
            extra['left'] = left_networks
        return s_flags, extra


class UpdateContainerState(ContainerBaseState):
    """
    Extends the base state by checking the current instance detail against the container configuration and volumes
    other containers. Also checks if the container image matches the configured image's id.
    """
    def __init__(self, *args, **kwargs):
        super(UpdateContainerState, self).__init__(*args, **kwargs)
        self.base_image_id = None
        self.volume_checker = None
        self.endpoint_registry = None
        self.current_commands = None

    def _check_links(self):
        instance_links = self.detail['HostConfig']['Links'] or []
        link_dict = defaultdict(set)
        for host_link in instance_links:
            link_name, __, link_alias = host_link.partition(':')
            link_dict[link_name[1:]].add(link_alias.rpartition('/')[2])
        for link in self.config.links:
            instance_aliases = link_dict.get(self.policy.cname(self.config_id.map_name, link.container))
            config_alias = link.alias or self.policy.get_hostname(link.container)
            if not instance_aliases or config_alias not in instance_aliases:
                log.debug("Checked link %s - could not find alias %s", link.container, config_alias)
                return False
            log.debug("Checked link %s - found alias %s", link.container, config_alias)
        return True

    def _check_commands(self, check_option):
        def _find_full_command(f_cmd, f_user):
            for __, c_user, c_cmd in self.current_commands:
                if c_user == f_user and c_cmd == f_cmd:
                    log.debug("Command for user %s found: %s.", c_user, c_cmd)
                    return True
            log.debug("Command for user %s not found: %s.", f_user, f_cmd)
            return False

        def _find_partial_command(f_cmd, f_user):
            for __, c_user, c_cmd in self.current_commands:
                if c_user == f_user and f_cmd in c_cmd:
                    log.debug("Command for user %s found: %s.", c_user, c_cmd)
                    return True
            log.debug("Command for user %s not found: %s.", f_user, f_cmd)
            return False

        def _cmd_running(cmd, cmd_user):
            res_cmd = resolve_value(cmd)
            if isinstance(res_cmd, (list, tuple)):
                res_cmd = ' '.join(res_cmd)
            if cmd_user is not None:
                res_user = resolve_value(cmd_user)
            else:
                res_user = extract_user(self.config.user)
            if res_user is None:
                res_user = 'root'
            log.debug("Looking up %s command for user %s: %s", check_option, res_user, res_cmd)
            return cmd_exists(res_cmd, res_user)

        if not self.config.exec_commands:
            return None
        if not self.current_commands:
            log.debug("No running exec commands found for container.")
            return self.config.exec_commands
        log.debug("Checking commands for container %s.", self.container_name)
        if check_option == CmdCheck.FULL:
            cmd_exists = _find_full_command
        elif check_option == CmdCheck.PARTIAL:
            cmd_exists = _find_partial_command
        else:
            log.debug("Invalid check mode %s - skipping.", check_option)
            return None
        return [exec_cmd for exec_cmd in self.config.exec_commands
                if not _cmd_running(exec_cmd.cmd, exec_cmd.user) and exec_cmd.policy != ExecPolicy.INITIAL]

    def _check_volumes(self):
        return self.volume_checker.check(self.config_id, self.container_map, self.config, self.detail)

    def _check_container_network_mode(self):
        net_mode = self.config.network_mode or 'default'
        if (net_mode == 'none') != self.detail['Config'].get('NetworkDisabled', False):
            return False
        instance_mode = self.detail['HostConfig'].get('NetworkMode') or 'default'
        if isinstance(net_mode, tuple):
            ref_mode = 'container:{0}'.format(self.policy.cname(self.config_id.map_name, *net_mode))
        else:
            ref_mode = net_mode
        return ref_mode == instance_mode

    def set_defaults(self):
        super(UpdateContainerState, self).set_defaults()
        self.current_commands = None

    def inspect(self):
        super(UpdateContainerState, self).inspect()
        if self.detail and self.detail['State']['Running'] and not self.config_flags & ConfigFlags.CONTAINER_ATTACHED:
            check_exec_option = self.options['check_exec_commands']
            if check_exec_option and check_exec_option != CmdCheck.NONE and self.config.exec_commands:
                self.current_commands = self.client.top(self.detail['Id'], ps_args='-eo pid,user,args')['Processes']

    def get_state(self):
        base_state, state_flags, extra = super(UpdateContainerState, self).get_state()
        if base_state == State.ABSENT or state_flags & StateFlags.NEEDS_RESET:
            return base_state, state_flags, extra

        config_id = self.config_id
        c_image_id = self.detail['Image']
        if self.config_flags & ConfigFlags.CONTAINER_ATTACHED:
            if self.options['update_persistent'] and c_image_id != self.base_image_id:
                return base_state, state_flags | StateFlags.IMAGE_MISMATCH, extra
            volumes = get_instance_volumes(self.detail)
            if volumes:
                mapped_path = resolve_value(self.container_map.volumes[config_id.instance_name])
                if self.container_map.use_attached_parent_name:
                    self.volume_checker.register_attached(mapped_path, volumes.get(mapped_path), config_id.instance_name,
                                                          config_id.config_name)
                else:
                    self.volume_checker.register_attached(mapped_path, volumes.get(mapped_path), config_id.instance_name)
        else:
            image_name = self.policy.image_name(self.config.image or config_id.config_name, self.container_map)
            images = self.policy.images[self.client_name]
            ref_image_id = images.ensure_image(image_name, pull=self.options['pull_before_update'],
                                               insecure_registry=self.options['pull_insecure_registry'])
            if c_image_id != ref_image_id and (not self.config.persistent or self.options['update_persistent']):
                state_flags |= StateFlags.IMAGE_MISMATCH
            if not self._check_volumes():
                state_flags |= StateFlags.VOLUME_MISMATCH
            if not self._check_links():
                state_flags |= StateFlags.MISSING_LINK
            if not (_check_environment(self.config, self.detail) and _check_cmd(self.config, self.detail) and
                    _check_container_network_ports(self.config, self.client_config, self.detail)):
                state_flags |= StateFlags.MISC_MISMATCH
            if base_state == State.RUNNING:
                check_exec_option = self.options['check_exec_commands']
                if check_exec_option:
                    missing_exec_cmds = self._check_commands(check_exec_option)
                    if missing_exec_cmds is not None:
                        state_flags |= StateFlags.EXEC_COMMANDS
                        extra['exec_commands'] = missing_exec_cmds
            if self.endpoint_registry:  # Client supports networking.
                net_s_flags, net_extra = self.endpoint_registry.check_container_config(config_id, self.config,
                                                                                       self.detail)
                state_flags |= net_s_flags
                extra.update(net_extra)
            elif not self._check_container_network_mode():
                state_flags |= StateFlags.MISC_MISMATCH
        return base_state, state_flags, extra


class UpdateNetworkState(NetworkBaseState):
    def __init__(self, *args, **kwargs):
        super(UpdateNetworkState, self).__init__(*args, **kwargs)
        self.endpoint_registry = None

    def get_state(self):
        base_state, state_flags, extra = super(UpdateNetworkState, self).get_state()
        if base_state == State.ABSENT or state_flags & StateFlags.NEEDS_RESET:
            return base_state, state_flags, extra

        self.endpoint_registry.register_network(self.detail)
        if (self.detail['Driver'] != resolve_value(self.config.driver) or
                not _check_network_driver_opts(self.config, self.detail) or
                self.detail['Internal'] != resolve_value(self.config.internal)):
            state_flags |= StateFlags.MISC_MISMATCH
        return base_state, state_flags, extra


class UpdateStateGenerator(DependencyStateGenerator):
    """
    Generates states for updating configured containers. Before checking each configuration, for each image the latest
    version is pulled from the registry, but only if :attr:`UpdateStateGenerator.pull_before_update` is set to ``True``.

    An attached container is considered outdated, if its image id does not correspond with the current base
    image, and :attr:`~ContainerUpdateMixin.update_persistent` is set to ``True``.
    Any other container is considered outdated, if

      - any of its attached volumes' paths does not match (i.e. they are not actually sharing the same virtual
        file system), or
      - the image id does not correspond with the configured image (e.g. because the image has been updated), or
      - environment variables have been changed in the configuration, or
      - command or entrypoint have been set or changed, or
      - network ports differ from what is specified in the configuration.

    In addition, the default state implementation applies, considering nonexistent containers or containers that
    cannot be restarted.
    """
    container_state_class = UpdateContainerState
    network_state_class = UpdateNetworkState

    pull_before_update = False
    pull_insecure_registry = False
    update_persistent = False
    check_exec_commands = CmdCheck.FULL
    policy_options = ['pull_before_update', 'pull_insecure_registry', 'update_persistent', 'check_exec_commands']

    def __init__(self, policy, kwargs):
        super(UpdateStateGenerator, self).__init__(policy, kwargs)
        self._base_image_ids = {
            client_name: policy.images[client_name].ensure_image(
                policy.image_name(policy.base_image), pull=self.pull_before_update,
                insecure_registry=self.pull_insecure_registry)
            for client_name in policy.clients.keys()
        }
        self._volume_checkers = {
            client_name: ContainerVolumeChecker()
            for client_name in policy.clients.keys()
        }
        default_network_details = {
            client_name: {
                n_name: client_config.get_client().inspect_network(n_name)
                for n_name in policy.default_network_names
                if n_name in policy.network_names[client_name]
            }
            for client_name, client_config in six.iteritems(policy.clients)
            if client_config.supports_networks
        }
        self._network_registries = {
            client_name: NetworkEndpointRegistry(policy.nname, policy.cname, policy.get_hostname,
                                                 default_network_details[client_name])
            for client_name, network_details in six.iteritems(default_network_details)
        }

    def get_container_state(self, client_name, *args, **kwargs):
        c_state = super(UpdateStateGenerator, self).get_container_state(client_name, *args, **kwargs)
        c_state.base_image_ids = self._base_image_ids[client_name]
        c_state.volume_checker = self._volume_checkers[client_name]
        c_state.endpoint_registry = self._network_registries.get(client_name)
        return c_state

    def get_network_state(self, client_name, *args, **kwargs):
        n_state = super(UpdateStateGenerator, self).get_network_state(client_name, *args, **kwargs)
        n_state.endpoint_registry = self._network_registries.get(client_name)
        return n_state
