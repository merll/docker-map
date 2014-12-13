# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from .actions import (ACTION_REMOVE, ACTION_CREATE, ACTION_START, ACTION_PREPARE, ACTION_STOP, ACTION_ATTACHED_FLAG,
                      ContainerAction)
from .base import BasePolicy, ForwardActionGeneratorMixin, AbstractActionGenerator
from .update import ContainerUpdateMixin
from .utils import INITIAL_START_TIME
from .simple import (SimpleCreateMixin, SimpleStartMixin, SimpleStopMixin, SimpleRemoveMixin,
                     SimpleShutdownMixin, SimpleRestartMixin)


class ResumeStartupGenerator(ForwardActionGeneratorMixin, AbstractActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(ResumeStartupGenerator, self).__init__(policy, *args, **kwargs)
        self._remove_status = policy.remove_status

    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        recreate_attached = False
        existing_containers = self._policy.container_names[map_name]
        for a in c_config.attaches:
            a_name = self._policy.cname(map_name, a)
            a_exists = a_name in existing_containers
            a_status = self._policy.container_detail[map_name](a_name)['State'] if a_exists else None
            a_running = a_status and a_status['Running']
            a_remove = a_exists and not a_running and a_status['ExitCode'] in self._remove_status
            if a_remove:
                yield ContainerAction(ACTION_REMOVE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                existing_containers.remove(a_name)
            a_create = not a_exists or a_remove
            if a_create:
                ac_kwargs = self._policy.get_attached_create_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_CREATE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ac_kwargs)
                existing_containers.add(a_name)
                recreate_attached = True
            a_start = a_create or a_status['StartedAt'] == INITIAL_START_TIME
            if a_start:
                yield ContainerAction(ACTION_START, ACTION_ATTACHED_FLAG | flags, map_name, a_name, None)
                ap_kwargs = self._policy.get_attached_prepare_kwargs(c_map, c_config, a)
                yield ContainerAction(ACTION_PREPARE, ACTION_ATTACHED_FLAG | flags, map_name, a_name, ap_kwargs)
        for ci in instances:
            ci_name = self._policy.cname(map_name, container_name, ci)
            ci_exists = ci_name in existing_containers
            ci_status = self._policy.container_detail[map_name](ci_name)['State'] if ci_exists else None
            ci_running = ci_status and ci_status['Running']
            ci_remove = ci_exists and not ci_running and ci_status['ExitCode'] in self._remove_status
            if ci_remove:
                ir_kwargs = self._policy.get_remove_kwargs(c_map, c_config)
                yield ContainerAction(ACTION_REMOVE, flags, map_name, ci_name, ir_kwargs)
                existing_containers.remove(ci_name)
            ci_create = not ci_exists or ci_remove
            if ci_create:
                ic_kwargs = self._policy.get_create_kwargs(c_map, c_config, container_name)
                yield ContainerAction(ACTION_CREATE, flags, map_name, ci_name, ic_kwargs)
                existing_containers.add(ci_name)
            ci_stop = recreate_attached and ci_running
            if ci_stop:
                ip_kwargs = self._policy.get_stop_kwargs(c_map, c_config, ci)
                yield ContainerAction(ACTION_STOP, flags, map_name, ci_name, ip_kwargs)
            needs_start = ci_create or ci_status['StartedAt'] == INITIAL_START_TIME if c_config.persistent else not ci_running
            ci_start = ci_create or ci_stop or needs_start
            if ci_start:
                is_kwargs = self._policy.get_start_kwargs(c_map, c_config, ci)
                yield ContainerAction(ACTION_START, flags, map_name, ci_name, is_kwargs)


class ResumeStartupMixin(object):
    remove_status = (-127, )

    def startup_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for restoring the running state of a configured container, including all of its dependencies.
        In detail, this means that:

        * Attached containers, if missing, are created and started. The same applies if the container exists but
          has failed to start (currently status -127).
        * Other containers are stopped, removed, and re-created if any of their attached containers has been
          (re-)created, or if they have an exit status indicating that they cannot be restarted (-127).
          Non-existing containers are created and started.

        :param map_name: Container map name.
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          updated.
        :type instances: list[unicode]
        :param kwargs: Has no effect in this implementation.
        """
        return ResumeStartupGenerator(self).get_actions(map_name, container, instances=instances, **kwargs)


class ResumeUpdatePolicy(SimpleCreateMixin, SimpleStartMixin, SimpleRestartMixin, SimpleStopMixin, SimpleRemoveMixin,
                         ResumeStartupMixin, SimpleShutdownMixin, ContainerUpdateMixin, BasePolicy):
    pass
