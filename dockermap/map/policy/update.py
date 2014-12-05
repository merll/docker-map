# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from .base import ForwardActionGeneratorMixin, AbstractActionGenerator
from . import (ContainerAction, ACTION_REMOVE, ACTION_ATTACHED_FLAG, ACTION_CREATE, ACTION_START, ACTION_PREPARE,
               ACTION_STOP)
from . import utils


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
        a_paths = dict((alias, utils.get_volume_path(c_map, alias)) for alias in c_config.attaches)
        for a in c_config.attaches:
            a_name = self._policy.cname(map_name, a)
            a_exists = a_name in self._policy.status
            if a_exists:
                a_detail = self._policy.status_detail[map_name](a_name)
                a_status = self._policy.status[a_name]
                a_image = a_detail['Image']
                a_remove = a_status in self.remove_status or a_image != self.base_image_ids[map_name]
                if a_remove:
                    yield ContainerAction(ACTION_REMOVE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                    ac_kwargs = self._policy.get_attached_create_kwargs(c_map, c_config, a)
                    yield ContainerAction(ACTION_CREATE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ac_kwargs)
                    yield ContainerAction(ACTION_START, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                    ap_kwargs = self._policy.get_attached_prepare_kwargs(c_map, c_config, a)
                    yield ContainerAction(ACTION_PREPARE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ap_kwargs)
                    current_attached_paths[a] = None
                else:
                    current_attached_paths[a] = a_detail['Volumes'].get(a_paths[a])
        image_name = self.iname_tag(c_map, c_config.image or container_name)
        image_id = self._policy.images[map_name](image_name)
        for ci in instances:
            ci_name = self._policy.cname(map_name, container_name, ci)
            ci_exists = ci_name in self._policy.status
            if ci_exists:
                ci_status = self._policy.status[ci_name]
                ci_detail = self._policy.status_detail[map_name](ci_name)
                ci_image = ci_detail['Image']
                path_mismatch = any(current_attached_paths.get(a) != ci_detail['Volumes'].get(a_path)
                                    for a, a_path in six.iteritems(a_paths))
                ci_remove = ci_status in self.remove_status or ci_image != image_id or path_mismatch
                if ci_remove:
                    if ci_status is True:
                        ip_kwargs = self._policy.get_stop_kwargs(c_map, c_config, ci)
                        yield ContainerAction(ACTION_STOP, flags, map_name, ci_name, ip_kwargs)
                    ir_kwargs = self._policy.get_remove_kwargs(c_map, c_config)
                    yield ContainerAction(ACTION_REMOVE, flags, map_name, ci_name, ir_kwargs)
                    ic_kwargs = self._policy.get_create_kwargs(c_map, c_config, container_name)
                    yield ContainerAction(ACTION_CREATE, flags, map_name, ci_name, ic_kwargs)
                    is_kwargs = self._policy.get_start_kwargs(c_map, c_config, ci)
                    yield ContainerAction(ACTION_START, flags, map_name, ci_name, is_kwargs)


class ContainerUpdateMixin(object):
    remove_status = (-127, )

    def update_actions(self, map_name, container, instances=None, **kwargs):
        return ContainerUpdateGenerator(self).get_actions(map_name, container, instances=instances, **kwargs)
