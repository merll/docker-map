# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools

from . import (ACTION_DEPENDENCY_FLAG, ACTION_ATTACHED_FLAG, ACTION_CREATE, ACTION_START, ACTION_PREPARE,
               ACTION_RESTART, ACTION_STOP, ACTION_REMOVE, ContainerAction)
from .base import BasePolicy, ForwardActionGeneratorMixin, AbstractActionGenerator, ReverseActionGeneratorMixin
from .utils import get_config


class SimpleCreateGenerator(ForwardActionGeneratorMixin, AbstractActionGenerator):
    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        for a in c_config.attaches:
            a_name = self._policy.cname(map_name, a)
            if a_name not in self._policy.status:
                a_kwargs = self._policy.get_attached_create_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_CREATE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, a_kwargs)
        for ci in instances:
            ci_name = self._policy.cname(map_name, container_name, ci)
            if ci_name not in self._policy.status:
                c_kwargs = self._policy.get_create_kwargs(c_map, c_config, container_name, kwargs)
                yield ContainerAction(ACTION_CREATE, flags, map_name, ci_name, c_kwargs)


class SimpleCreateMixin(object):
    def create_actions(self, map_name, container, instances=None, **kwargs):
        return SimpleCreateGenerator(self).get_actions(map_name, container, instances=instances, **kwargs)


class SimpleStartGenerator(ForwardActionGeneratorMixin, AbstractActionGenerator):
    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        for a in c_config.attaches:
            a_name = self._policy.cname(map_name, a)
            a_status = self._policy.status.get(a_name)
            if a_status != 0 and a_status is not True:
                yield ContainerAction(ACTION_START, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                ca_kwargs = self._policy.get_attached_prepare_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_PREPARE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ca_kwargs)
        for instance in instances:
            ci_name = self._policy.cname(map_name, container_name, instance)
            if self._policy.status.get(ci_name) is not True:
                c_kwargs = self._policy.get_start_kwargs(c_map, c_config, instance, kwargs)
                yield ContainerAction(ACTION_START, flags, map_name, ci_name, c_kwargs)


class SimpleStartMixin(object):
    def start_actions(self, map_name, container, instances=None, **kwargs):
        return SimpleStartGenerator(self).get_actions(map_name, container, instances=instances, **kwargs)


class SimpleRestartMixin(object):
    def restart_actions(self, map_name, container, instances=None, **kwargs):
        c_map = self._maps[map_name]
        c_config = get_config(c_map, container)
        c_instances = instances or c_config.instances or [None]
        for instance in c_instances:
            ci_name = self.cname(map_name, container, instance)
            if self._status.get(ci_name) is True:
                c_kwargs = self.get_restart_kwargs(c_map, c_config, instance, kwargs)
                yield ContainerAction(ACTION_RESTART, 0, map_name, ci_name, c_kwargs)


class SimpleStopGenerator(ReverseActionGeneratorMixin, AbstractActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(SimpleStopGenerator, self).__init__(policy, *args, **kwargs)
        self._stop_dependent = policy.stop_dependent

    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        if self._stop_dependent or not flags & ACTION_DEPENDENCY_FLAG:
            for instance in instances:
                ci_name = self._policy.cname(map_name, container_name, instance)
                if self._policy.status.get(ci_name) is True:
                    c_kwargs = self._policy.get_stop_kwargs(c_map, c_config, instance, kwargs)
                    yield ContainerAction(ACTION_STOP, flags, map_name, ci_name, c_kwargs)


class SimpleStopMixin(object):
    stop_dependent = True

    def stop_actions(self, map_name, container, instances=None, **kwargs):
        return SimpleStopGenerator(self).get_actions(map_name, container, instances=instances, **kwargs)


class SimpleRemoveGenerator(ReverseActionGeneratorMixin, AbstractActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(SimpleRemoveGenerator, self).__init__(policy, *args, **kwargs)
        self._remove_dependent = policy.remove_dependent
        self._remove_persistent = policy.remove_persistent
        self._remove_attached = policy.remove_attached

    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        if (self._remove_dependent or not flags & ACTION_DEPENDENCY_FLAG) and (self._remove_persistent or not c_config.persistent):
            for instance in instances:
                ci_name = self._policy.cname(map_name, container_name, instance)
                if ci_name in self._policy.status:
                    yield ContainerAction(ACTION_REMOVE, flags, map_name, ci_name, kwargs)
            if self._remove_attached:
                for a in c_config.attaches:
                    a_name = self._policy.cname(map_name, a)
                    if a_name in self._policy.status:
                        a_kwargs = self._policy.get_remove_kwargs(c_map, c_config, kwargs)
                        yield ContainerAction(ACTION_REMOVE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, a_kwargs)


class SimpleRemoveMixin(object):
    remove_dependent = True
    remove_persistent = True
    remove_attached = False

    def remove_actions(self, map_name, container, instances=None, **kwargs):
        return SimpleRemoveGenerator(self).get_actions(map_name, container, instances=instances, **kwargs)


class SimpleStartupMixin(object):
    def startup_actions(self, map_name, container, instances=None, **kwargs):
        return itertools.chain(self.create_actions(map_name, container, instances),
                               self.start_actions(map_name, container, instances))


class SimpleShutdownMixin(object):
    def shutdown_actions(self, map_name, container, instances=None, **kwargs):
        return itertools.chain(self.stop_actions(map_name, container, instances),
                               self.remove_actions(map_name, container, instances))


class SimplePolicy(SimpleCreateMixin, SimpleStartMixin, SimpleRestartMixin, SimpleStopMixin, SimpleRemoveMixin,
                   SimpleStartupMixin, SimpleShutdownMixin, BasePolicy):
    pass
