# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from .actions import (ACTION_REMOVE, ACTION_CREATE, ACTION_START, ACTION_PREPARE, ACTION_STOP, ACTION_ATTACHED_FLAG,
                      ContainerAction)
from .base import BasePolicy, BaseActionMixin
from .simple import (SimpleCreateMixin, SimpleStartMixin, SimpleStopMixin, SimpleRemoveMixin,
                     SimpleShutdownMixin, SimpleRestartMixin)


class ResumeStartupMixin(BaseActionMixin):
    remove_status = (-127, )

    def _start(self, map_name, c_map, container_name, c_config, instances, flags=0, **kwargs):
        recreate_attached = False
        for a in c_config.attaches:
            a_name = self.cname(map_name, a)
            a_exists = a_name in self._status
            a_status = self._status[a_name] if a_exists else None
            a_remove = a_exists and a in self.remove_status
            if a_remove:
                yield ContainerAction(ACTION_REMOVE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
            a_create = not a_exists or a_remove
            if a_create:
                ac_kwargs = self.get_attached_create_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_CREATE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ac_kwargs)
                recreate_attached = True
            a_start = a_create or a_status is False or a_status is None
            if a_start:
                yield ContainerAction(ACTION_START, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                ap_kwargs = self.get_attached_prepare_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_PREPARE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ap_kwargs)
        for ci in instances:
            ci_name = self.cname(map_name, container_name, ci)
            ci_exists = ci_name in self._status
            ci_status = self._status[ci_name] if ci_exists else None
            ci_remove = ci_exists and ci_status in self.remove_status
            if ci_remove:
                ir_kwargs = self.get_remove_kwargs(c_map, c_config)
                yield ContainerAction(ACTION_REMOVE, flags, map_name, ci_name, ir_kwargs)
            ci_create = not ci_exists or ci_remove
            if ci_create:
                ic_kwargs = self.get_create_kwargs(c_map, c_config, container_name)
                yield ContainerAction(ACTION_CREATE, flags, map_name, ci_name, ic_kwargs)
            ci_stop = recreate_attached and ci_status is True
            if ci_stop:
                ip_kwargs = self.get_stop_kwargs(c_map, c_config, ci)
                yield ContainerAction(ACTION_STOP, flags, map_name, ci_name, ip_kwargs)
            needs_start = ci_status is False or ci_status is None if c_config.persistent else ci_status is not True
            ci_start = ci_create or ci_stop or needs_start
            if ci_start:
                is_kwargs = self.get_start_kwargs(c_map, c_config, ci)
                yield ContainerAction(ACTION_START, flags, map_name, ci_name, is_kwargs)

    def startup_actions(self, map_name, container, instances=None, **kwargs):
        return self.get_base_actions(self._start, map_name, container, instances=instances, **kwargs)


class ResumePolicy(SimpleCreateMixin, SimpleStartMixin, SimpleRestartMixin, SimpleStopMixin, SimpleRemoveMixin,
                   ResumeStartupMixin, SimpleShutdownMixin, BasePolicy):
    pass
