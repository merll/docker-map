# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools

from .actions import (ACTION_CREATE_DEPENDENCY_ATTACHED, ACTION_CREATE_DEPENDENCY, ACTION_CREATE_ATTACHED,
                      ACTION_CREATE, ACTION_START_DEPENDENCY_ATTACHED, ACTION_PREPARE_DEPENDENCY_ATTACHED,
                      ACTION_START_DEPENDENCY, ACTION_START_ATTACHED, ACTION_PREPARE_ATTACHED, ACTION_START,
                      ACTION_STOP_DEPENDENT, ACTION_STOP, ACTION_REMOVE_DEPENDENT, ACTION_REMOVE_DEPENDENT_ATTACHED,
                      ACTION_REMOVE, ACTION_REMOVE_ATTACHED, ACTION_RESTART, ContainerAction)
from .base import BasePolicy
from .utils import get_existing_containers, get_config, get_running_containers


class SimpleCreateMixin(object):
    def create_actions(self, map_name, container, instances=None, **kwargs):
        c_map = self._maps[map_name]
        dependencies = self.get_dependencies(map_name, container)
        existing_containers = get_existing_containers(self._status)
        for d_map_name, d_container, d_instance in dependencies:
            d_map = self._maps[d_map_name]
            d_config = get_config(d_map, d_container)
            for a in d_config.attaches:
                da_name = self.cname(d_map_name, a)
                if da_name not in existing_containers:
                    da_kwargs = self.get_attached_create_kwargs(d_map, d_config, a)
                    yield ContainerAction(ACTION_CREATE_DEPENDENCY_ATTACHED, d_map_name, da_name, da_kwargs)
            d_instances = [d_instance] if d_instance else d_config.instances or [None]
            for di in d_instances:
                di_name = self.cname(d_map_name, d_container, di)
                if di_name not in existing_containers:
                    d_kwargs = self.get_create_kwargs(d_map, d_config, d_container)
                    yield ContainerAction(ACTION_CREATE_DEPENDENCY, d_map_name, di_name, d_kwargs)
        c_config = get_config(c_map, container)
        for a in c_config.attaches:
            ca_name = self.cname(map_name, a)
            if ca_name not in existing_containers:
                ca_kwargs = self.get_attached_create_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_CREATE_ATTACHED, map_name, ca_name, ca_kwargs)
        c_instances = instances or c_config.instances or [None]
        for instance in c_instances:
            ci_name = self.cname(map_name, container, instance)
            if ci_name not in existing_containers:
                c_kwargs = self.get_create_kwargs(c_map, c_config, container, kwargs)
                yield ContainerAction(ACTION_CREATE, map_name, ci_name, c_kwargs)


class SimpleStartMixin(object):
    def start_actions(self, map_name, container, instances=None, **kwargs):
        c_map = self._maps[map_name]
        dependencies = self.get_dependencies(map_name, container)
        running_containers = get_running_containers(self._status)
        for d_map_name, d_container, d_instance in dependencies:
            d_map = self._maps[d_map_name]
            d_config = get_config(d_map, d_container)
            for a in d_config.attaches:
                da_name = self.cname(d_map_name, a)
                if da_name not in running_containers:
                    yield ContainerAction(ACTION_START_DEPENDENCY_ATTACHED, d_map_name, da_name, None)
                    da_kwargs = self.get_attached_prepare_kwargs(d_map, d_config, a)
                    yield ContainerAction(ACTION_PREPARE_DEPENDENCY_ATTACHED, d_map_name, da_name, da_kwargs)
            d_instances = [d_instance] if d_instance else d_config.instances or [None]
            for di in d_instances:
                di_name = self.cname(d_map_name, d_container, di)
                if di_name not in running_containers:
                    d_kwargs = self.get_start_kwargs(d_map, d_config, di)
                    yield ContainerAction(ACTION_START_DEPENDENCY, d_map_name, di_name, d_kwargs)
        c_config = get_config(c_map, container)
        for a in c_config.attaches:
            ca_name = self.cname(map_name, a)
            if ca_name not in running_containers:
                yield ContainerAction(ACTION_START_ATTACHED, map_name, ca_name, None)
                ca_kwargs = self.get_attached_prepare_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_PREPARE_ATTACHED, map_name, ca_name, ca_kwargs)
        c_instances = instances or c_config.instances or [None]
        for instance in c_instances:
            ci_name = self.cname(map_name, container, instance)
            if ci_name not in running_containers:
                c_kwargs = self.get_start_kwargs(c_map, c_config, instance, kwargs)
                yield ContainerAction(ACTION_START, map_name, ci_name, c_kwargs)


class SimpleRestartMixin(object):
    def restart(self, map_name, container, instances=None, **kwargs):
        c_map = self._maps[map_name]
        running_containers = get_running_containers(self._status)
        c_config = get_config(c_map, container)
        c_instances = instances or c_config.instances or [None]
        for instance in c_instances:
            ci_name = self.cname(map_name, container, instance)
            if ci_name in running_containers:
                c_kwargs = self.get_restart_kwargs(c_map, c_config, instance, kwargs)
                yield ContainerAction(ACTION_RESTART, map_name, ci_name, c_kwargs)


class SimpleStopMixin(object):
    stop_dependent = True

    def stop_actions(self, map_name, container, instances=None, **kwargs):
        c_map = self._maps[map_name]
        dependencies = self.get_dependencies(map_name, container)
        running_containers = get_running_containers(self._status)
        if self.stop_dependent:
            for d_map_name, d_container, d_instance in dependencies:
                d_map = self._maps[d_map_name]
                d_config = get_config(d_map, d_container)
                d_instances = [d_instance] if d_instance else d_config.instances or [None]
                for di in d_instances:
                    di_name = self.cname(d_map_name, d_container, di)
                    if di_name in running_containers:
                        d_kwargs = self.get_stop_kwargs(d_map, d_config, di, kwargs)
                        yield ContainerAction(ACTION_STOP_DEPENDENT, d_map_name, di_name, d_kwargs)
        c_config = get_config(c_map, container)
        c_instances = instances or c_config.instances or [None]
        for instance in c_instances:
            ci_name = self.cname(map_name, container, instance)
            if ci_name in running_containers:
                c_kwargs = self.get_stop_kwargs(c_map, c_config, instance, kwargs)
                yield ContainerAction(ACTION_STOP, map_name, ci_name, c_kwargs)


class SimpleRemoveMixin(object):
    remove_dependent = True
    remove_attached = False

    def remove_actions(self, map_name, container, instances=None, **kwargs):
        c_map = self._maps[map_name]
        dependencies = self.get_dependencies(map_name, container)
        existing_containers = get_existing_containers(self._status)
        if self.remove_dependent:
            for d_map_name, d_container, d_instance in dependencies:
                d_map = self._maps[d_map_name]
                d_config = get_config(d_map, d_container)
                d_instances = [d_instance] if d_instance else d_config.instances or [None]
                for di in d_instances:
                    di_name = self.cname(d_map_name, d_container, di)
                    if di_name in existing_containers:
                        d_kwargs = self.get_remove_kwargs(d_map, d_config, kwargs)
                        yield ContainerAction(ACTION_REMOVE_DEPENDENT, d_map_name, di_name, d_kwargs)
                if self.remove_attached:
                    for a in d_config.attaches:
                        da_name = self.cname(d_map_name, a)
                        if da_name in existing_containers:
                            yield ContainerAction(ACTION_REMOVE_DEPENDENT_ATTACHED, d_map_name, da_name, kwargs)
        c_config = get_config(c_map, container)
        c_instances = instances or c_config.instances or [None]
        for instance in c_instances:
            ci_name = self.cname(map_name, container, instance)
            if ci_name in existing_containers:
                yield ContainerAction(ACTION_REMOVE, map_name, ci_name, kwargs)
        if self.remove_attached:
            for a in c_config.attaches:
                ca_name = self.cname(map_name, a)
                if ca_name in existing_containers:
                    c_kwargs = self.get_remove_kwargs(c_map, c_config, kwargs)
                    yield ContainerAction(ACTION_REMOVE_ATTACHED, map_name, ca_name, c_kwargs)


class SimpleStartupMixin(SimpleCreateMixin, SimpleStartMixin):
    def startup_actions(self, map_name, container, instances=None, **kwargs):
        return itertools.chain(self.create_actions(map_name, container, instances),
                               self.start_actions(map_name, container, instances))


class SimpleShutdownMixin(SimpleStopMixin, SimpleRemoveMixin):
    def shutdown_actions(self, map_name, container, instances=None, **kwargs):
        return itertools.chain(self.stop_actions(map_name, container, instances),
                               self.remove_actions(map_name, container, instances))


class SimplePolicy(SimpleStartupMixin, SimpleShutdownMixin, SimpleRestartMixin, BasePolicy):
    pass
