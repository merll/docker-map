# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from .base import ForwardActionGeneratorMixin, AbstractActionGenerator
from . import (ContainerAction, ACTION_REMOVE, ACTION_ATTACHED_FLAG, ACTION_CREATE, ACTION_START, ACTION_PREPARE,
               ACTION_STOP)


class ContainerUpdateGenerator(ForwardActionGeneratorMixin, AbstractActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(ContainerUpdateGenerator, self).__init__(policy, *args, **kwargs)
        self.remove_status = policy.remove_status
        self.base_image_ids = dict((map_name, self._policy.images[map_name](self.iname_tag(map_, self._policy.base_image)))
                                   for map_name, map_ in six.iteritems(self._policy.container_maps))

    def iname_tag(self, container_map, image):
        i_name = ':'.join((image, 'latest')) if ':' not in image else image
        return self._policy.iname(container_map, i_name)

    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        current_attached_paths = dict()
        a_paths = dict((alias, c_map.volumes[alias]) for alias in c_config.attaches)
        existing_containers = self._policy.container_names[map_name]
        for a in c_config.attaches:
            a_name = self._policy.cname(map_name, a)
            a_exists = a_name in existing_containers
            if a_exists:
                a_detail = self._policy.container_detail[map_name](a_name)
                a_status = a_detail['State']
                a_image = a_detail['Image']
                a_remove = (not a_status['Running'] and a_status['ExitCode'] in self.remove_status) or \
                    a_image != self.base_image_ids[map_name]
                if a_remove:
                    yield ContainerAction(ACTION_REMOVE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                    existing_containers.remove(a_name)
                    ac_kwargs = self._policy.get_attached_create_kwargs(c_map, c_config, a)
                    yield ContainerAction(ACTION_CREATE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ac_kwargs)
                    existing_containers.add(a_name)
                    yield ContainerAction(ACTION_START, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                    ap_kwargs = self._policy.get_attached_prepare_kwargs(c_map, c_config, a)
                    yield ContainerAction(ACTION_PREPARE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ap_kwargs)
                    current_attached_paths[a] = None
                else:
                    volumes = a_detail.get('Volumes')
                    mapped_path = a_paths[a]
                    current_attached_paths[mapped_path] = volumes.get(mapped_path) if volumes else None
        image_name = self.iname_tag(c_map, c_config.image or container_name)
        image_id = self._policy.images[map_name](image_name)
        for ci in instances:
            ci_name = self._policy.cname(map_name, container_name, ci)
            ci_exists = ci_name in existing_containers
            if ci_exists:
                ci_detail = self._policy.container_detail[map_name](ci_name)
                ci_status = ci_detail['State']
                ci_image = ci_detail['Image']
                ci_volumes = ci_detail.get('Volumes') or dict()
                path_mismatch = any(current_attached_paths.get(a_path) != ci_volumes.get(a_path)
                                    for a, a_path in six.iteritems(a_paths))
                ci_remove = (not ci_status['Running'] and ci_status['ExitCode'] in self.remove_status) or \
                    ci_image != image_id or path_mismatch
                if ci_remove:
                    if ci_status['Running']:
                        ip_kwargs = self._policy.get_stop_kwargs(c_map, c_config, ci)
                        yield ContainerAction(ACTION_STOP, flags, map_name, ci_name, ip_kwargs)
                    ir_kwargs = self._policy.get_remove_kwargs(c_map, c_config)
                    yield ContainerAction(ACTION_REMOVE, flags, map_name, ci_name, ir_kwargs)
                    existing_containers.remove(ci_name)
                    ic_kwargs = self._policy.get_create_kwargs(c_map, c_config, container_name)
                    yield ContainerAction(ACTION_CREATE, flags, map_name, ci_name, ic_kwargs)
                    existing_containers.add(ci_name)
                    is_kwargs = self._policy.get_start_kwargs(c_map, c_config, ci)
                    yield ContainerAction(ACTION_START, flags, map_name, ci_name, is_kwargs)


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
        """
        return ContainerUpdateGenerator(self).get_actions(map_name, container, instances=instances, **kwargs)
