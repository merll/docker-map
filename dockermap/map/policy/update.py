# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import defaultdict
import logging
import shlex
import six

from ...functional import resolve_value
from ..input import EXEC_POLICY_INITIAL
from .base import (AttachedPreparationMixin, ExecMixin, ForwardActionGeneratorMixin, SignalMixin,\
                   AbstractDependentActionGenerator)
from . import utils

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

    create_options = utils.init_options(c_config.create_options)
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
    create_options = utils.init_options(c_config.create_options)
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
            bind_path, host_path = utils.get_shared_volume_path(self._container_map, shared_volume.volume, instance)
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
        instance_volumes = utils.get_instance_volumes(instance_detail)
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


class ContainerUpdateGenerator(AttachedPreparationMixin, ExecMixin, SignalMixin, ForwardActionGeneratorMixin,
                               AbstractDependentActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(ContainerUpdateGenerator, self).__init__(policy, *args, **kwargs)
        self.remove_status = policy.remove_status
        self.pull_before_update = policy.pull_before_update
        self.pull_insecure_registry = policy.pull_insecure_registry
        self.update_persistent = policy.update_persistent
        self.check_commands = policy.check_exec_commands
        self.base_image_ids = {
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

    def _run_missing_commands(self, container_map, config_name, container_config, client_name, client_config, client,
                              container_name, instance_name):
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

        if not self.check_commands or self.check_commands == CMD_CHECK_NONE or not container_config.exec_commands:
            return
        log.debug("Checking commands for container %s.", container_name)
        current_commands = client.top(container_name, ps_args='-eo pid,user,args')['Processes']
        if self.check_commands == CMD_CHECK_FULL:
            cmd_exists = _find_full_command
        elif self.check_commands == CMD_CHECK_PARTIAL:
            cmd_exists = _find_partial_command
        else:
            log.debug("Invalid check mode %s - skipping.", self.check_commands)
            return
        for cmd, cmd_user, cmd_policy in container_config.exec_commands:
            if cmd_policy == EXEC_POLICY_INITIAL:
                continue
            res_cmd = resolve_value(cmd)
            if isinstance(res_cmd, (list, tuple)):
                res_cmd = ' '.join(res_cmd)
            if cmd_user is not None:
                res_user = resolve_value(cmd_user)
            else:
                res_user = utils.extract_user(container_config.user)
            if res_user is None:
                res_user = 'root'
            log.debug("Looking up %s command for user %s: %s", self.check_commands, res_user, res_cmd)
            if not cmd_exists(res_cmd, res_user):
                log.debug("Not found.")
                self.exec_single_command(container_map, config_name, container_config, client_name, client_config,
                                         client, container_name, instance_name, cmd, cmd_user)

    def generate_item_actions(self, map_name, c_map, config_name, c_config, instances, flags, *args, **kwargs):
        a_paths = {alias: resolve_value(c_map.volumes[alias]) for alias in c_config.attaches}
        for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
            use_host_config = utils.use_host_config(client)
            images = self._policy.images[client_name]
            existing_containers = self._policy.container_names[client_name]
            a_parent = config_name if c_map.use_attached_parent_name else None
            for a in c_config.attaches:
                a_name = self._policy.aname(map_name, a, a_parent)
                log.debug("Checking attached container %s.", a_name)
                a_exists = a_name in existing_containers
                if a_exists:
                    a_detail = client.inspect_container(a_name)
                    a_status = a_detail['State']
                    a_image = a_detail['Image']
                    log.debug("Container from image %s found with status\n%s.", a_image, a_status)
                    a_remove = ((not a_status['Running'] and a_status['ExitCode'] in self.remove_status) or
                                (self.update_persistent and a_image != self.base_image_ids[client_name]))
                    if a_remove:
                        log.debug("Found to be outdated or non-restartable - removing.")
                        ar_kwargs = self._policy.get_remove_kwargs(c_map, config_name, c_config, client_name,
                                                                   client_config, a_name)
                        client.remove_container(**ar_kwargs)
                        existing_containers.remove(a_name)
                else:
                    log.debug("Container not found.")
                    a_remove = False
                    a_detail = None
                if a_remove or not a_exists:
                    log.debug("Creating and starting attached container %s.", a_name)
                    ac_kwargs = self._policy.get_attached_create_kwargs(c_map, config_name, c_config, client_name,
                                                                        client_config, a_name, a,
                                                                        include_host_config=use_host_config)
                    client.create_container(**ac_kwargs)
                    existing_containers.add(a_name)

                    if use_host_config:
                        as_kwargs = dict(container=a_name)
                    else:
                        as_kwargs = self._policy.get_attached_host_config_kwargs(c_map, config_name, c_config,
                                                                                 client_name, client_config, a_name, a)
                    client.start(**as_kwargs)
                    self.prepare_container(c_map, config_name, c_config, client_name, client_config, client, a,
                                           a_name)
                else:
                    volumes = utils.get_instance_volumes(a_detail)
                    if volumes:
                        mapped_path = a_paths[a]
                        self._volume_checker.register_attached(mapped_path, volumes.get(mapped_path), a, a_parent)
            image_name = self._policy.image_name(c_config.image or config_name, c_map)
            image_id = images.ensure_image(image_name, pull=self.pull_before_update,
                                           insecure_registry=self.pull_insecure_registry)
            for ci in instances:
                ci_name = self._policy.cname(map_name, config_name, ci)
                ci_exists = ci_name in existing_containers
                log.debug("Checking container %s.", ci_name)
                if ci_exists:
                    ci_detail = client.inspect_container(ci_name)
                    ci_status = ci_detail['State']
                    ci_image = ci_detail['Image']
                    ci_running = ci_status['Running']
                    log.debug("Container from image %s found with status\n%s.", ci_image, ci_status)
                    ci_remove = ((not ci_running and ci_status['ExitCode'] in self.remove_status) or
                                 ((not c_config.persistent or self.update_persistent) and ci_image != image_id) or
                                 not self._volume_checker.check(c_map, c_config, config_name, ci, ci_detail) or
                                 not self._check_links(map_name, c_config, ci_detail) or
                                 not _check_environment(c_config, ci_detail) or
                                 not _check_cmd(c_config, ci_detail) or
                                 not _check_network(c_config, client_config, ci_detail))
                    if ci_remove:
                        log.debug("Found to be outdated or non-restartable - removing.")
                        if ci_running:
                            self.signal_stop(c_map, config_name, c_config, client_name, client_config, client,
                                             ci_name, ci)
                        ir_kwargs = self._policy.get_remove_kwargs(c_map, config_name, c_config, client_name,
                                                                   client_config, ci_name)
                        client.remove_container(**ir_kwargs)
                        existing_containers.remove(ci_name)
                        ci_create = True
                        ci_start = True
                        ci_initial = True
                    else:
                        ci_create = False
                        ci_initial = utils.is_initial(ci_status)
                        ci_start = ci_initial if c_config.persistent else not ci_running
                else:
                    log.debug("Container not found.")
                    ci_create = True
                    ci_start = True
                    ci_initial = True
                if ci_create:
                    log.debug("Creating container %s.", ci_name)
                    ic_kwargs = self._policy.get_create_kwargs(c_map, config_name, c_config, client_name,
                                                               client_config, ci_name, ci,
                                                               include_host_config=use_host_config)
                    yield client_name, client.create_container(**ic_kwargs)
                    existing_containers.add(ci_name)
                if ci_create or ci_start:
                    log.debug("Starting container %s.", ci_name)
                    if use_host_config:
                        is_kwargs = dict(container=ci_name)
                    else:
                        is_kwargs = self._policy.get_host_config_kwargs(c_map, config_name, c_config, client_name,
                                                                        client_config, ci_name, ci)
                    client.start(**is_kwargs)
                    self.exec_container_commands(c_map, config_name, c_config, client_name, client_config, client,
                                                 ci_name, ci, ci_initial)
                elif ci_running:
                    self._run_missing_commands(c_map, config_name, c_config, client_name, client_config, client,
                                               ci_name, ci)


class ContainerUpdateMixin(object):
    remove_status = (-127, -1)
    pull_before_update = False
    pull_insecure_registry = False
    update_persistent = False
    check_exec_commands = CMD_CHECK_FULL

    def update_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for updating a configured container, including all of its dependencies. Updating in this case
        means that:

        * For each image the default tag (e.g. ``latest``) is pulled from the registry, but only if
          :attr:`~ContainerUpdateMixin.pull_before_update` is set to ``True``.
        * An attached container is removed and re-created if its image id does not correspond with the current base
          image, or the status indicates that the container cannot be restarted (-127 in this implementation).
          Attached and `persistent` images are not updated in case of image changes, unless
          :attr:`~ContainerUpdateMixin.update_persistent` is set to ``True``.
        * Any other container is re-created if

          - any of its attached volumes' paths does not match (i.e. they are not actually sharing the same virtual
            file system), or
          - the container cannot be restarted (the error status indicates so), or
          - the image id does not correspond with the configured image (e.g. because the image has been updated), or
          - environment variables have been changed in the configuration, or
          - command or entrypoint have been set or changed, or
          - network ports differ from what is specified in the configuration.

        Only prior existing containers are removed and re-created. Any created container is also started by its
        configuration.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          updated.
        :type instances: list[unicode]
        :param kwargs: Has no effect in this implementation.
        :return: Return values of created main containers.
        :rtype: list[(unicode, dict)]
        """
        return ContainerUpdateGenerator(self).get_all_actions(map_name, container, instances=instances, **kwargs)
