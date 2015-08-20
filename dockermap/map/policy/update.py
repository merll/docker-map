# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import shlex
import six

from ...functional import resolve_value
from .base import AttachedPreparationMixin, ForwardActionGeneratorMixin, AbstractActionGenerator
from . import utils


log = logging.getLogger(__name__)


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


class ContainerUpdateGenerator(AttachedPreparationMixin, ForwardActionGeneratorMixin, AbstractActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(ContainerUpdateGenerator, self).__init__(policy, *args, **kwargs)
        self.remove_status = policy.remove_status
        self.pull_latest = policy.pull_latest
        self.pull_insecure_registry = policy.pull_insecure_registry
        self.update_persistent = policy.update_persistent
        self.base_image_ids = {
            client_name: policy.images[client_name].ensure_image(
                self.iname_tag(policy.base_image), pull_latest=self.pull_latest,
                insecure_registry=self.pull_insecure_registry)
            for client_name in policy.clients.keys()
        }
        self.path_vfs = {}

    def _check_links(self, map_name, c_config, instance_detail):
        def _extract_link_info(host_link):
            link_name, __, link_alias = host_link.partition(':')
            return link_name[1:], link_alias.rpartition('/')[2]

        instance_links = instance_detail['HostConfig']['Links'] or []
        linked_dict = dict(map(_extract_link_info, instance_links))
        for link in c_config.links:
            if link.alias != linked_dict.get(self._policy.cname(map_name, link.container)):
                return False
        return True

    def _check_volumes(self, c_map, c_config, config_name, instance_name, instance_detail):
        def _validate_bind(b_config, b_instance):
            for shared_volume in b_config.binds:
                bind_path, host_path = utils.get_shared_volume_path(c_map, shared_volume.volume, b_instance)
                instance_vfs = instance_volumes.get(bind_path)
                log.debug("Checking host bind. Config / container instance:\n%s\n%s", host_path, instance_vfs)
                if not (instance_vfs and host_path == instance_vfs):
                    return False
                self.path_vfs[config_name, instance_name, bind_path] = instance_vfs
            return True

        def _validate_attached(a_config):
            for attached in a_config.attaches:
                attached_path = resolve_value(c_map.volumes[attached])
                instance_vfs = instance_volumes.get(attached_path)
                attached_vfs = self.path_vfs.get((attached, None, attached_path))
                log.debug("Checking attached %s path. Attached instance / dependent container instance:\n%s\n%s",
                          attached, attached_vfs, instance_vfs)
                if not (instance_vfs and attached_vfs == instance_vfs):
                    return False
                self.path_vfs[config_name, instance_name, attached_path] = instance_vfs
            return True

        def _check_config_paths(cr_config, cr_instance):
            for share in cr_config.shares:
                cr_shared_path = resolve_value(share)
                self.path_vfs[config_name, instance_name, cr_shared_path] = instance_volumes.get(share)
            if not _validate_bind(cr_config, cr_instance):
                return False
            if not _validate_attached(cr_config):
                return False
            for used in cr_config.uses:
                used_volume = used.volume
                used_path = resolve_value(c_map.volumes.get(used_volume))
                if used_path:
                    used_vfs = self.path_vfs.get((used_volume, None, used_path))
                    instance_path = instance_volumes.get(used_path)
                    log.debug("Checking used %s path. Parent instance / dependent container instance:\n%s\n%s",
                              used.volume, used_vfs, instance_path)
                    if used_vfs != instance_path:
                        return False
                    continue
                ref_c_name, ref_i_name = self._policy.resolve_cname(used_volume, False)
                log.debug("Looking up dependency %s (instance %s).", ref_c_name, ref_i_name)
                ref_config = c_map.get_existing(ref_c_name)
                if ref_config:
                    for share in ref_config.shares:
                        ref_shared_path = resolve_value(share)
                        i_shared_path = instance_volumes.get(ref_shared_path)
                        shared_vfs = self.path_vfs.get((ref_c_name, ref_i_name, ref_shared_path))
                        log.debug("Checking shared path %s. Parent instance / dependent container instance:\n%s\n%s",
                                  share, shared_vfs, i_shared_path)
                        if shared_vfs != i_shared_path:
                            return False
                        self.path_vfs[(config_name, instance_name, ref_shared_path)] = i_shared_path
                    _validate_bind(ref_config, ref_i_name)
                    _validate_attached(ref_config)
                else:
                    raise ValueError("Volume alias or container reference could not be resolved: {0}".format(used))
            return True

        instance_volumes = instance_detail.get('Volumes') or {}
        return _check_config_paths(c_config, instance_name)

    def iname_tag(self, image, container_map=None):
        i_name = '{0}:latest'.format(image) if ':' not in image else image
        if container_map:
            return self._policy.iname(container_map, i_name)
        return i_name

    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        a_paths = {alias: resolve_value(c_map.volumes[alias]) for alias in c_config.attaches}
        for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
            use_host_config = utils.use_host_config(client)
            images = self._policy.images[client_name]
            existing_containers = self._policy.container_names[client_name]
            a_parent = container_name if c_map.use_attached_parent_name else None
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
                        ar_kwargs = self._policy.get_remove_kwargs(c_map, container_name, c_config, client_name,
                                                                   client_config, a_name)
                        client.remove_container(**ar_kwargs)
                        existing_containers.remove(a_name)
                else:
                    log.debug("Container not found.")
                    a_remove = False
                    a_detail = None
                if a_remove or not a_exists:
                    log.debug("Creating and starting attached container %s.", a_name)
                    ac_kwargs = self._policy.get_attached_create_kwargs(c_map, container_name, c_config, client_name,
                                                                        client_config, a_name, a,
                                                                        include_host_config=use_host_config)
                    client.create_container(**ac_kwargs)
                    existing_containers.add(a_name)

                    if use_host_config:
                        as_kwargs = dict(container=a_name)
                    else:
                        as_kwargs = self._policy.get_attached_host_config_kwargs(c_map, container_name, c_config,
                                                                                 client_name, client_config, a_name, a)
                    client.start(**as_kwargs)
                    self.prepare_container(c_map, container_name, c_config, client_name, client_config, client, a,
                                           a_name)
                else:
                    volumes = a_detail.get('Volumes')
                    if volumes:
                        mapped_path = a_paths[a]
                        self.path_vfs[a, None, mapped_path] = volumes.get(mapped_path)
            image_name = self.iname_tag(c_config.image or container_name, container_map=c_map)
            image_id = images.ensure_image(image_name, pull_latest=self.pull_latest,
                                           insecure_registry=self.pull_insecure_registry)
            for ci in instances:
                ci_name = self._policy.cname(map_name, container_name, ci)
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
                                 not self._check_volumes(c_map, c_config, container_name, ci, ci_detail) or
                                 not self._check_links(map_name, c_config, ci_detail) or
                                 not _check_environment(c_config, ci_detail) or
                                 not _check_cmd(c_config, ci_detail) or
                                 not _check_network(c_config, client_config, ci_detail))
                    if ci_remove:
                        log.debug("Found to be outdated or non-restartable - removing.")
                        if ci_running:
                            ip_kwargs = self._policy.get_stop_kwargs(c_map, container_name, c_config, client_name,
                                                                     client_config, ci_name, ci)
                            client.stop(**ip_kwargs)
                        ir_kwargs = self._policy.get_remove_kwargs(c_map, container_name, c_config, client_name,
                                                                   client_config, ci_name)
                        client.remove_container(**ir_kwargs)
                        existing_containers.remove(ci_name)
                        ci_create = True
                        ci_start = True
                    else:
                        ci_create = False
                        ci_start = utils.is_initial(ci_status) if c_config.persistent else not ci_running
                else:
                    log.debug("Container not found.")
                    ci_create = True
                    ci_start = True
                if ci_create:
                    log.debug("Creating container %s.", ci_name)
                    ic_kwargs = self._policy.get_create_kwargs(c_map, container_name, c_config, client_name,
                                                               client_config, ci_name, ci,
                                                               include_host_config=use_host_config)
                    yield client_name, client.create_container(**ic_kwargs)
                    existing_containers.add(ci_name)
                if ci_create or ci_start:
                    log.debug("Starting container %s.", ci_name)
                    if use_host_config:
                        is_kwargs = dict(container=ci_name)
                    else:
                        is_kwargs = self._policy.get_host_config_kwargs(c_map, container_name, c_config, client_name,
                                                                        client_config, ci_name, ci)
                    client.start(**is_kwargs)


class ContainerUpdateMixin(object):
    remove_status = (-127, -1, )
    pull_latest = False
    pull_insecure_registry = False
    update_persistent = False

    def update_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for updating a configured container, including all of its dependencies. Updating in this case
        means that:

        * For each image the latest version is pulled from the registry, but only if
          :attr:`~ContainerUpdateMixin.pull_latest` is set to ``True``.
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          updated.
        :type instances: list[unicode]
        :param kwargs: Has no effect in this implementation.
        :return: Return values of created main containers.
        :rtype: list[(unicode, dict)]
        """
        return ContainerUpdateGenerator(self).get_actions(map_name, container, instances=instances, **kwargs)
