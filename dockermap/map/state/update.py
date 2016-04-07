# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import defaultdict
import logging
import shlex
import six

from dockermap.map.policy.utils import init_options, get_shared_volume_path, get_instance_volumes, extract_user
from .base import DependencyStateGenerator
from ...functional import resolve_value
from ..policy import CONFIG_FLAG_ATTACHED
from . import STATE_FLAG_OUTDATED, STATE_ABSENT

log = logging.getLogger(__name__)

CMD_CHECK_FULL = 'full'
CMD_CHECK_PARTIAL = 'partial'
CMD_CHECK_NONE = 'none'


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


def _check_cmd(c_config, instance_detail):
    create_options = init_options(c_config.create_options)
    if not create_options:
        return True
    instance_config = instance_detail['Config']
    config_cmd = resolve_value(create_options.get('command')) if create_options else None
    if config_cmd:
        instance_cmd = instance_config['Cmd'] or []
        log.debug("Checking command. Config / container instance:\n%s\n%s", config_cmd, instance_cmd)
        if isinstance(config_cmd, six.string_types):
            if shlex.split(config_cmd) != instance_cmd:
                return False
        elif list(config_cmd) != instance_cmd:
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


def _check_network(container_config, client_config, instance_detail):
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


class SingleContainerVfsCheck(object):
    """
    :type vfs_paths: dict[tuple, unicode | str]
    :type container_map: dockermap.map.container.ContainerMap
    :type config_name: unicode | str
    :type instance_name: unicode | str
    :type instance_volumes: dict[unicode | str, unicode | str]
    """
    def __init__(self, vfs_paths, container_map, config_name, instance_name, instance_volumes):
        self._vfs_paths = vfs_paths
        self._instance_volumes = instance_volumes
        self._container_map = container_map
        self._config_name = config_name
        self._instance_name = instance_name
        self._use_parent_name = container_map.use_attached_parent_name
        self._volumes = container_map.volumes

    def check_bind(self, config, instance):
        for shared_volume in config.binds:
            bind_path, host_path = get_shared_volume_path(self._container_map, shared_volume.volume, instance)
            instance_vfs = self._instance_volumes.get(bind_path)
            log.debug("Checking host bind. Config / container instance:\n%s\n%s", host_path, instance_vfs)
            if not (instance_vfs and host_path == instance_vfs):
                return False
            self._vfs_paths[self._config_name, self._instance_name, bind_path] = instance_vfs
        return True

    def check_attached(self, config, parent_name):
        for attached in config.attaches:
            a_name = '{0}.{1}'.format(parent_name, attached) if self._use_parent_name else attached
            attached_path = resolve_value(self._volumes[attached])
            instance_vfs = self._instance_volumes.get(attached_path)
            attached_vfs = self._vfs_paths.get((a_name, None, attached_path))
            log.debug("Checking attached %s path. Attached instance / dependent container instance:\n%s\n%s",
                      attached, attached_vfs, instance_vfs)
            if not (instance_vfs and attached_vfs == instance_vfs):
                return False
            self._vfs_paths[self._config_name, self._instance_name, attached_path] = instance_vfs
        return True

    def check_used(self, config):
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
                    self._vfs_paths[(self._config_name, self._instance_name, ref_shared_path)] = i_shared_path
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

    def check(self, container_map, container_config, config_name, instance_name, instance_detail):
        instance_volumes = get_instance_volumes(instance_detail)
        vfs = SingleContainerVfsCheck(self._vfs_paths, container_map, container_config, instance_name, instance_volumes)
        for share in container_config.shares:
            cr_shared_path = resolve_value(share)
            self._vfs_paths[config_name, instance_name, cr_shared_path] = instance_volumes.get(share)
        if not vfs.check_bind(container_config, instance_name):
            return False
        if not vfs.check_attached(container_config, config_name):
            return False
        if not vfs.check_used(container_config):
            return False
        return True


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
    pull_before_update = False
    pull_insecure_registry = False
    update_persistent = False
    check_exec_commands = CMD_CHECK_FULL
    policy_options = ['pull_before_update', 'pull_insecure_registry', 'update_persistent', 'check_exec_commands']

    def __init__(self, policy, kwargs):
        super(UpdateStateGenerator, self).__init__(policy, kwargs)
        self._base_image_ids = {
            client_name: policy.images[client_name].ensure_image(
                policy.image_name(policy.base_image), pull=self.pull_before_update,
                insecure_registry=self.pull_insecure_registry)
            for client_name in policy.clients.keys()
        }
        self._volume_checker = ContainerVolumeChecker()

    def _check_links(self, map_name, c_config, instance_detail):
        instance_links = instance_detail['HostConfig']['Links'] or []
        link_dict = defaultdict(set)
        for host_link in instance_links:
            link_name, __, link_alias = host_link.partition(':')
            link_dict[link_name[1:]].add(link_alias.rpartition('/')[2])
        for link in c_config.links:
            instance_aliases = link_dict.get(self._policy.cname(map_name, link.container))
            if not instance_aliases or link.alias not in instance_aliases:
                log.debug("Checked link %s - could not find alias %s", link.container, link.alias)
                return False
            log.debug("Checked link %s - found alias %s", link.container, link.alias)
        return True

    def _check_commands(self, container_config, client, container_name):
        def _find_full_command(f_cmd, f_user):
            for __, c_user, c_cmd in current_commands:
                if c_user == f_user and c_cmd == f_cmd:
                    log.debug("Command for user %s found: %s.", c_user, c_cmd)
                    return True
            return False

        def _find_partial_command(f_cmd, f_user):
            for __, c_user, c_cmd in current_commands:
                if c_user == f_user and f_cmd in c_cmd:
                    log.debug("Command for user %s found: %s.", c_user, c_cmd)
                    return True
            return False

        def _cmd_state(cmd, cmd_user):
            res_cmd = resolve_value(cmd)
            if isinstance(res_cmd, (list, tuple)):
                res_cmd = ' '.join(res_cmd)
            if cmd_user is not None:
                res_user = resolve_value(cmd_user)
            else:
                res_user = extract_user(container_config.user)
            if res_user is None:
                res_user = 'root'
            log.debug("Looking up %s command for user %s: %s", self.check_exec_commands, res_user, res_cmd)
            return cmd_exists(res_cmd, res_user)

        log.debug("Checking commands for container %s.", container_name)
        current_commands = client.top(container_name, ps_args='-eo pid,user,args')['Processes']
        if self.check_exec_commands == CMD_CHECK_FULL:
            cmd_exists = _find_full_command
        elif self.check_exec_commands == CMD_CHECK_PARTIAL:
            cmd_exists = _find_partial_command
        else:
            log.debug("Invalid check mode %s - skipping.", self.check_exec_commands)
            return None
        return [(exec_cmd, _cmd_state(exec_cmd[0], exec_cmd[1])) for exec_cmd in container_config.exec_commands]

    def get_container_state(self, map_name, container_map, config_name, container_config, client_name, client_config,
                            client, instance_alias, config_flags=0):
        """
        Extends the base state by checking the current instance detail against the container configuration and volumes
        other containers. Also checks if the container image matches the configured image's id.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param client: Docker client.
        :type client: docker.client.Client
        :param instance_alias: Container instance name or attached alias.
        :type instance_alias: unicode | str
        :param config_flags: Config flags on the container.
        :type config_flags: bool
        :return: Tuple of container inspection detail, and the base state information derived from that.
        :rtype: (dict | NoneType, unicode | str, int, dict | NoneType)
        """
        detail, base_state, state_flags, extra = super(
            UpdateStateGenerator, self).get_container_state(map_name, container_map, config_name, container_config,
                                                            client_name, client_config, client, instance_alias,
                                                            config_flags=config_flags)
        if base_state == STATE_ABSENT:
            return detail, base_state, state_flags, extra

        c_image_id = detail['Image']
        if config_flags & CONFIG_FLAG_ATTACHED:
            if self.update_persistent and c_image_id != self._base_image_ids[client_name]:
                return detail, base_state, state_flags | STATE_FLAG_OUTDATED, extra
            volumes = get_instance_volumes(detail)
            if volumes:
                mapped_path = resolve_value(container_map.volumes[instance_alias])
                if container_map.use_attached_parent_name:
                    self._volume_checker.register_attached(mapped_path, volumes.get(mapped_path), instance_alias,
                                                           config_name)
                else:
                    self._volume_checker.register_attached(mapped_path, volumes.get(mapped_path), instance_alias)
        else:
            image_name = self._policy.image_name(container_config.image or config_name, container_map)
            images = self._policy.images[client_name]
            ref_image_id = images.ensure_image(image_name, pull=self.pull_before_update,
                                               insecure_registry=self.pull_insecure_registry)
            if not (((container_config.persistent and not self.update_persistent) or c_image_id == ref_image_id) and
                    self._volume_checker.check(container_map, container_config, config_name, instance_alias, detail) and
                    self._check_links(map_name, container_config, detail) and
                    _check_environment(container_config, detail) and
                    _check_cmd(container_config, detail) and
                    _check_network(container_config, client_config, detail)):
                return detail, base_state, state_flags | STATE_FLAG_OUTDATED, extra
            if (self.check_exec_commands and self.check_exec_commands != CMD_CHECK_NONE and
                    container_config.exec_commands):
                exec_results = self._check_commands(container_config, client, detail['Id'])
                if exec_results is not None:
                    extra.update(exec_commands=exec_results)
        return detail, base_state, state_flags, extra
