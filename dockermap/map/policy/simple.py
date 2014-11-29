# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools

from . import (ACTION_DEPENDENCY_FLAG, ACTION_ATTACHED_FLAG, ACTION_CREATE, ACTION_START, ACTION_PREPARE,
               ACTION_RESTART, ACTION_STOP, ACTION_REMOVE, ContainerAction)
from .base import BasePolicy, BaseActionMixin
from .utils import get_config


class SimpleCreateMixin(BaseActionMixin):
    def _create_actions(self, map_name, c_map, container_name, c_config, instances, flags=0, **kwargs):
        for a in c_config.attaches:
            a_name = self.cname(map_name, a)
            if a_name not in self._status:
                a_kwargs = self.get_attached_create_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_CREATE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, a_kwargs)
        for ci in instances:
            ci_name = self.cname(map_name, container_name, ci)
            if ci_name not in self._status:
                c_kwargs = self.get_create_kwargs(c_map, c_config, container_name, kwargs)
                yield ContainerAction(ACTION_CREATE, flags, map_name, ci_name, c_kwargs)

    def create_actions(self, map_name, container, instances=None, **kwargs):
        return self.get_base_actions(self._create_actions, map_name, container, instances=instances, **kwargs)


class SimpleStartMixin(BaseActionMixin):
    def _start_actions(self, map_name, c_map, container_name, c_config, instances, flags=0, **kwargs):
        for a in c_config.attaches:
            a_name = self.cname(map_name, a)
            a_status = self._status.get(a_name)
            if a_status != 0 and a_status is not True:
                yield ContainerAction(ACTION_START, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                ca_kwargs = self.get_attached_prepare_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_PREPARE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ca_kwargs)
        for instance in instances:
            ci_name = self.cname(map_name, container_name, instance)
            if self._status.get(ci_name) is not True:
                c_kwargs = self.get_start_kwargs(c_map, c_config, instance, kwargs)
                yield ContainerAction(ACTION_START, flags, map_name, ci_name, c_kwargs)

    def start_actions(self, map_name, container, instances=None, **kwargs):
        return self.get_base_actions(self._start_actions, map_name, container, instances=instances, **kwargs)


class SimpleRestartMixin(object):
    def restart(self, map_name, container, instances=None, **kwargs):
        c_map = self._maps[map_name]
        c_config = get_config(c_map, container)
        c_instances = instances or c_config.instances or [None]
        for instance in c_instances:
            ci_name = self.cname(map_name, container, instance)
            if self._status.get(ci_name) is True:
                c_kwargs = self.get_restart_kwargs(c_map, c_config, instance, kwargs)
                yield ContainerAction(ACTION_RESTART, 0, map_name, ci_name, c_kwargs)


class SimpleStopMixin(BaseActionMixin):
    stop_dependent = True

    def _stop_actions(self, map_name, c_map, container_name, c_config, instances, flags=0, **kwargs):
        if self.stop_dependent or not flags & ACTION_DEPENDENCY_FLAG:
            for instance in instances:
                ci_name = self.cname(map_name, container_name, instance)
                if self._status.get(ci_name) is True:
                    c_kwargs = self.get_stop_kwargs(c_map, c_config, instance, kwargs)
                    yield ContainerAction(ACTION_STOP, flags, map_name, ci_name, c_kwargs)

    def stop_actions(self, map_name, container, instances=None, **kwargs):
        return self.get_base_actions(self._stop_actions, map_name, container, instances=instances, **kwargs)


class SimpleRemoveMixin(BaseActionMixin):
    remove_dependent = True
    remove_persistent = True
    remove_attached = False

    def _remove_actions(self, map_name, c_map, container_name, c_config, instances, flags=0, **kwargs):
        if (self.remove_dependent or not flags & ACTION_DEPENDENCY_FLAG) and (self.remove_persistent or not c_config.persistent):
            for instance in instances:
                ci_name = self.cname(map_name, container_name, instance)
                if ci_name in self._status:
                    yield ContainerAction(ACTION_REMOVE, flags, map_name, ci_name, kwargs)
            if self.remove_attached:
                for a in c_config.attaches:
                    a_name = self.cname(map_name, a)
                    if a_name in self._status:
                        a_kwargs = self.get_remove_kwargs(c_map, c_config, kwargs)
                        yield ContainerAction(ACTION_REMOVE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, a_kwargs)

    def remove_actions(self, map_name, container, instances=None, **kwargs):
        return self.get_base_actions(self._remove_actions, map_name, container, instances=instances, **kwargs)


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
