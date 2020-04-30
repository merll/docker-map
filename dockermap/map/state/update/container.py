# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import shlex
from collections import defaultdict

import six
from docker import utils as docker_utils

from ....functional import resolve_value
from ....utils import format_image_tag
from ...input import ItemType, CmdCheck, ExecPolicy
from ...policy.utils import get_instance_volumes, extract_user, init_options
from .. import StateFlags, State
from ..base import ContainerBaseState


log = logging.getLogger(__name__)


CONTAINER_UPDATE_VARS = [
    # Key in inspect output, docker-py kwarg, whether to also check create kwargs, check client for constraints support,
    # conversion function
    ('BlkioWeight', 'blkio_weight', False, False, None),
    ('CpuPeriod', 'cpu_period', False, True, None),
    ('CpuQuota', 'cpu_quota', False, True, None),
    ('CpuShares', 'cpu_shares', True, True, None),
    ('CpusetCpus', 'cpuset_cpus', False, True, None),
    ('CpusetMems', 'cpuset_mems', False, True, None),
    ('Memory', 'mem_limit', True, True, docker_utils.parse_bytes),
    ('MemoryReservation', 'mem_reservation', False, False, docker_utils.parse_bytes),
    ('MemorySwap', 'memswap_limit', True, True, docker_utils.parse_bytes),
    ('KernelMemory', 'kernel_memory', False, True, docker_utils.parse_bytes),
    ('OomKillDisable', 'oom_kill_disable', False, True, None),
    ('PidsLimit', 'pids_limit', False, True, None),
]


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


def _check_limits(container_config, instance_detail, client_config):
    constraints = client_config.constraints
    i_host_config = instance_detail['HostConfig']
    c_host_config = container_config.host_config
    c_create_options = container_config.create_options
    update_dict = {}
    needs_reset = False
    for inspect_key, config_key, check_co, check_cs, input_func in CONTAINER_UPDATE_VARS:
        if check_cs and not constraints.get(config_key):
            log.debug("Skipping check for {0} - not supported by the client.".format(config_key))
            continue
        i_value = i_host_config.get(inspect_key) or None
        c_value = c_host_config.get(config_key) or None
        if not c_value and check_co:
            c_value = c_create_options.get(config_key) or None
        if config_key == 'memswap_limit' and not c_value:
            # Has a dependent default value.
            mem = c_host_config.get('mem_limit') or c_create_options.get('mem_limit')
            if mem:
                c_value = docker_utils.parse_bytes(mem) * 2
        if c_value and input_func:
            c_value = input_func(c_value)
        if i_value or c_value:
            log.debug("Comparing host-config variable %s - Container: %s - Config: %s.", inspect_key, i_value, c_value)
            if i_value != c_value:
                if c_value is not None:
                    log.debug("Updating %s to %s.", inspect_key, c_value)
                    update_dict[config_key] = c_value
                else:
                    # The API implementation (maybe just docker-py) will discard empty default values.
                    log.debug("Host-config variable %s cannot be reset to default, suggesting container reset.",
                              inspect_key)
                    needs_reset = True
    return update_dict, needs_reset


def _check_restart_policy(container_config, instance_detail):
    c_restart_policy = container_config.host_config.get('restart_policy')
    i_restart_policy = instance_detail['HostConfig'].get('RestartPolicy')
    if c_restart_policy and i_restart_policy:
        cr_name = c_restart_policy.get('Name')
        ir_name = i_restart_policy.get('Name')
        if cr_name == 'on-failure':
            if ir_name == 'on-failure':
                rp_update = c_restart_policy.get('MaximumRetryCount', 0) != i_restart_policy.get('MaximumRetryCount', 0)
            else:
                rp_update = True
        else:
            rp_update = cr_name != ir_name
    else:
        rp_update = False
    if rp_update:
        return {'restart_policy': c_restart_policy}
    return {}


class UpdateContainerState(ContainerBaseState):
    """
    Extends the base state by checking the current instance detail against the container configuration and volumes
    other containers. Also checks if the container image matches the configured image's id.
    """
    def __init__(self, *args, **kwargs):
        super(UpdateContainerState, self).__init__(*args, **kwargs)
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
        instance_volumes = get_instance_volumes(self.detail, self.client_config.features['volumes'])
        return self.volume_checker.check(self.config_id, self.container_map, self.config, instance_volumes)

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
        if self.detail and self.detail['State']['Running'] and self.config_id.config_type == ItemType.CONTAINER:
            check_exec_option = self.options['check_exec_commands']
            if check_exec_option and check_exec_option != CmdCheck.NONE and self.config.exec_commands:
                self.current_commands = self.client.top(self.detail['Id'], ps_args='-eo pid,user,args')['Processes']

    def get_state(self):
        base_state, state_flags, extra = super(UpdateContainerState, self).get_state()
        if base_state == State.ABSENT or state_flags & StateFlags.NEEDS_RESET:
            return base_state, state_flags, extra

        config_id = self.config_id
        c_image_id = self.detail['Image']
        if config_id.config_type == ItemType.VOLUME:
            volumes = get_instance_volumes(self.detail, False)
            if volumes:
                default_paths = self.policy.default_volume_paths[config_id.map_name]
                if self.container_map.use_attached_parent_name:
                    volume_name = '{0}.{1}'.format(config_id.config_name, config_id.instance_name)
                else:
                    volume_name = config_id.instance_name
                mapped_path = resolve_value(default_paths[volume_name])
                self.volume_checker.register_attached(volume_name, mapped_path, volumes.get(mapped_path))
        else:
            image_name = format_image_tag(self.container_map.get_image(self.config.image or config_id.config_name))
            images = self.policy.images[self.client_name]
            ref_image_id = images.get(image_name)
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
                    if missing_exec_cmds:
                        state_flags |= StateFlags.EXEC_COMMANDS
                        extra['exec_commands'] = missing_exec_cmds
            if self.endpoint_registry:  # Client supports networking.
                net_s_flags, net_extra = self.endpoint_registry.check_container_config(config_id, self.config,
                                                                                       self.detail)
                state_flags |= net_s_flags
                extra.update(net_extra)
            elif not self._check_container_network_mode():
                state_flags |= StateFlags.MISC_MISMATCH
            hc_update, hc_needs_reset = _check_limits(self.config, self.detail, self.client_config)
            restart_policy_update = _check_restart_policy(self.config, self.detail)
            hc_update.update(restart_policy_update)
            if not self.client_config.features['container_update_restart_policy'] and restart_policy_update:
                hc_needs_reset = True
            if hc_update:
                if not self.client_config.features['container_update']:
                    hc_needs_reset = True
                state_flags |= StateFlags.HOST_CONFIG_UPDATE
                extra['update_container'] = hc_update
            if hc_needs_reset:
                if not self.options['skip_limit_reset']:
                    state_flags |= StateFlags.MISC_MISMATCH
                else:
                    log.info("Container has a different host-config that cannot be update, but is not reset.")
        return base_state, state_flags, extra
