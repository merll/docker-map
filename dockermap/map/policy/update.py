# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from .base import AttachedPreparationMixin, ForwardActionGeneratorMixin, AbstractActionGenerator


class ContainerUpdateGenerator(AttachedPreparationMixin, ForwardActionGeneratorMixin, AbstractActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(ContainerUpdateGenerator, self).__init__(policy, *args, **kwargs)
        self.remove_status = policy.remove_status
        self.base_image_ids = dict((client_name, policy.images[client_name].ensure_image(
            self.iname_tag(policy.base_image))) for client_name, __ in six.iteritems(policy.clients))
        self.path_vfs = dict()

    def _check_links(self, map_name, c_config, instance_links):
        def _extract_link_info(host_link):
            link_name, __, link_alias = host_link.partition(':')
            return link_name[1:], link_alias.rpartition('/')[2]

        linked_dict = dict(map(_extract_link_info, instance_links))
        for link in c_config.links:
            if link.alias != linked_dict.get(self._policy.cname(map_name, link.container)):
                return False
        return True

    def _check_volumes(self, c_map, c_config, config_name, instance_name, instance_volumes):
        def _validate_bind(b_config, b_instance):
            for host_bind in b_config.binds:
                bind_alias = host_bind[0]
                bind_path = c_map.volumes[bind_alias]
                bind_vfs = instance_volumes.get(bind_path)
                if c_map.host.get(bind_alias, b_instance) != bind_vfs:
                    return False
                self.path_vfs[config_name, instance_name, bind_path] = bind_vfs

        def _validate_attached(a_config):
            for attached in a_config.attaches:
                attached_path = c_map.volumes[attached]
                attached_vfs = instance_volumes.get(attached_path)
                if self.path_vfs.get((attached, None, attached_path)) != attached_vfs:
                    return False
                self.path_vfs[config_name, instance_name, attached_path] = attached_vfs

        def _check_config_paths(cr_config, cr_instance):
            for share in cr_config.shares:
                self.path_vfs[config_name, instance_name, share] = instance_volumes.get(share)
            _validate_bind(cr_config, cr_instance)
            _validate_attached(cr_config)
            for used in cr_config.uses:
                used_path = c_map.volumes.get(used)
                if used_path:
                    if self.path_vfs.get((used, None, used_path)) != instance_volumes.get(used_path):
                        return False
                    continue
                ref_c_name, ref_i_name = self._policy.resolve_cname(used, False)
                ref_config = c_map.get_existing(ref_c_name)
                if ref_config:
                    for share in ref_config.shares:
                        shared_path = instance_volumes.get(share)
                        if self.path_vfs.get((ref_c_name, ref_i_name, share)) != shared_path:
                            return False
                        self.path_vfs[(config_name, instance_name, share)] = shared_path
                    _validate_bind(ref_config, ref_i_name)
                    _validate_attached(ref_config)
                else:
                    raise ValueError("Volume alias or container reference could not be resolved: {0}".format(used))
            return True

        return _check_config_paths(c_config, instance_name)

    def iname_tag(self, image, container_map=None):
        i_name = ':'.join((image, 'latest')) if ':' not in image else image
        if container_map:
            return self._policy.iname(container_map, i_name)
        return i_name

    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        a_paths = dict((alias, c_map.volumes[alias]) for alias in c_config.attaches)
        for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
            images = self._policy.images[client_name]
            existing_containers = self._policy.container_names[client_name]
            for a in c_config.attaches:
                a_name = self._policy.cname(map_name, a)
                a_exists = a_name in existing_containers
                if a_exists:
                    a_detail = client.inspect_container(a_name)
                    a_status = a_detail['State']
                    a_image = a_detail['Image']
                    a_remove = (not a_status['Running'] and a_status['ExitCode'] in self.remove_status) or \
                        a_image != self.base_image_ids[client_name]
                    if a_remove:
                        ar_kwargs = self._policy.get_remove_kwargs(c_map, c_config, client_name, client_config, a_name)
                        client.remove_container(**ar_kwargs)
                        existing_containers.remove(a_name)
                else:
                    a_remove = False
                    a_detail = None
                if a_remove or not a_exists:
                    ac_kwargs = self._policy.get_attached_create_kwargs(c_map, c_config, client_name, client_config,
                                                                        a_name, a)
                    client.create_container(**ac_kwargs)
                    existing_containers.add(a_name)
                    as_kwargs = self._policy.get_attached_start_kwargs(c_map, c_config, client_name, client_config,
                                                                       a_name, a)
                    client.start(**as_kwargs)
                    self.prepare_container(images, client, c_map, c_config, client_name, client_config, a, a_name)
                else:
                    volumes = a_detail.get('Volumes')
                    if volumes:
                        mapped_path = a_paths[a]
                        self.path_vfs[a, None, mapped_path] = volumes.get(mapped_path)
            image_name = self.iname_tag(c_config.image or container_name, container_map=c_map)
            image_id = self._policy.images[client_name].ensure_image(image_name)
            for ci in instances:
                ci_name = self._policy.cname(map_name, container_name, ci)
                ci_exists = ci_name in existing_containers
                if ci_exists:
                    ci_detail = client.inspect_container(ci_name)
                    ci_status = ci_detail['State']
                    ci_image = ci_detail['Image']
                    ci_volumes = ci_detail.get('Volumes') or dict()
                    ci_links = ci_detail['HostConfig']['Links'] or []
                    ci_remove = (not ci_status['Running'] and ci_status['ExitCode'] in self.remove_status) or \
                        ci_image != image_id or \
                        not self._check_volumes(c_map, c_config, container_name, ci, ci_volumes) or \
                        not self._check_links(map_name, c_config, ci_links)
                    if ci_remove:
                        if ci_status['Running']:
                            ip_kwargs = self._policy.get_stop_kwargs(c_map, c_config, client_name, client_config,
                                                                     ci_name, ci)
                            client.stop(**ip_kwargs)
                        ir_kwargs = self._policy.get_remove_kwargs(c_map, c_config, client_name, client_config, ci_name)
                        client.remove_container(**ir_kwargs)
                        existing_containers.remove(ci_name)
                else:
                    ci_remove = False
                if ci_remove or not ci_exists:
                    ic_kwargs = self._policy.get_create_kwargs(c_map, c_config, client_name, client_config, ci_name,
                                                               container_name)
                    yield client_name, client.create_container(**ic_kwargs)
                    existing_containers.add(ci_name)
                    is_kwargs = self._policy.get_start_kwargs(c_map, c_config, client_name, client_config, ci_name, ci)
                    client.start(**is_kwargs)


class ContainerUpdateMixin(object):
    remove_status = (-127, )

    def update_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for updating a configured container, including all of its dependencies. Updating in this case
        means that:

        * An attached container is removed and re-created if its image id does not correspond with the current base
          image, or the status indicates that the container cannot be restarted (-127 in this implementation).
        * Any other container is re-created if any of its attached volumes' paths does not match (i.e. they are not
          actually sharing the same virtual file system), the container cannot be restarted, or if the image id does
          not correspond with the configured image (e.g. because the image has been updated).

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
