# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from .base import (BasePolicy, AttachedPreparationMixin, ExecMixin, ForwardActionGeneratorMixin,
                   AbstractDependentActionGenerator)
from .script import ScriptMixin
from .simple import (SimpleCreateMixin, SimpleStartMixin, SimpleStopMixin, SimpleRemoveMixin,
                     SimpleShutdownMixin, SimpleRestartMixin)
from .update import ContainerUpdateMixin
from . import utils


class ResumeStartupGenerator(AttachedPreparationMixin, ExecMixin, ForwardActionGeneratorMixin,
                             AbstractDependentActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(ResumeStartupGenerator, self).__init__(policy, *args, **kwargs)
        self._remove_status = policy.remove_status

    def generate_item_actions(self, map_name, c_map, config_name, c_config, instances, flags, *args, **kwargs):
        recreate_attached = False
        for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
            use_host_config = utils.use_host_config(client)
            existing_containers = self._policy.container_names[client_name]
            images = self._policy.images[client_name]
            a_parent = config_name if c_map.use_attached_parent_name else None
            for a in c_config.attaches:
                a_name = self._policy.aname(map_name, a, a_parent)
                a_exists = a_name in existing_containers
                a_status = client.inspect_container(a_name)['State'] if a_exists else None
                a_running = a_status and a_status['Running']
                a_remove = a_exists and not a_running and a_status['ExitCode'] in self._remove_status
                if a_remove:
                    ar_kwargs = self._policy.get_remove_kwargs(c_map, config_name, c_config, client_name,
                                                               client_config, a_name)
                    client.remove_container(**ar_kwargs)
                    existing_containers.remove(a_name)
                a_create = not a_exists or a_remove
                if a_create:
                    ac_kwargs = self._policy.get_attached_create_kwargs(c_map, config_name, c_config, client_name,
                                                                        client_config, a_name, a,
                                                                        include_host_config=use_host_config)
                    images.ensure_image(ac_kwargs['image'])
                    client.create_container(**ac_kwargs)
                    existing_containers.add(a_name)
                    recreate_attached = True
                a_start = a_create or utils.is_initial(a_status)
                if a_start:
                    if use_host_config:
                        as_kwargs = dict(container=a_name)
                    else:
                        as_kwargs = self._policy.get_attached_host_config_kwargs(c_map, config_name, c_config,
                                                                                 client_name, client_config, a_name, a)
                    client.start(**as_kwargs)
                    self.prepare_container(c_map, config_name, c_config, client_name, client_config, client, a,
                                           a_name)
            for ci in instances:
                ci_name = self._policy.cname(map_name, config_name, ci)
                ci_exists = ci_name in existing_containers
                ci_status = client.inspect_container(ci_name)['State'] if ci_exists else None
                ci_running = ci_status and ci_status['Running']
                ci_stop = recreate_attached and ci_running
                if ci_stop:
                    ip_kwargs = self._policy.get_stop_kwargs(c_map, config_name, c_config, client_name,
                                                             client_config, ci_name, ci)
                    client.stop(**ip_kwargs)
                ci_remove = ci_exists and (not ci_running and ci_status['ExitCode'] in self._remove_status) or ci_stop
                if ci_remove:
                    ir_kwargs = self._policy.get_remove_kwargs(c_map, config_name, c_config, client_name,
                                                               client_config, ci_name)
                    client.remove_container(**ir_kwargs)
                    existing_containers.remove(ci_name)
                ci_create = not ci_exists or ci_remove
                if ci_create:
                    ic_kwargs = self._policy.get_create_kwargs(c_map, config_name, c_config, client_name,
                                                               client_config, ci_name, ci,
                                                               include_host_config=use_host_config)
                    images.ensure_image(ic_kwargs['image'])
                    yield client_name, client.create_container(**ic_kwargs)
                    existing_containers.add(ci_name)
                is_initial = ci_create or utils.is_initial(ci_status)
                needs_start = is_initial if c_config.persistent else not ci_running
                ci_start = ci_stop or needs_start
                if ci_start:
                    if use_host_config:
                        is_kwargs = dict(container=ci_name)
                    else:
                        is_kwargs = self._policy.get_host_config_kwargs(c_map, config_name, c_config, client_name,
                                                                        client_config, ci_name, ci)
                    client.start(**is_kwargs)
                    self.exec_container_commands(c_map, config_name, c_config, client_name, client_config, client,
                                                 ci_name, ci, is_initial)


class ResumeStartupMixin(object):
    remove_status = (-127, -1)

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
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          updated.
        :type instances: list[unicode | str]
        :param kwargs: Has no effect in this implementation.
        :return: Return values of created main containers.
        :rtype: list[(unicode | str, dict)]
        """
        return ResumeStartupGenerator(self).get_all_actions(map_name, container, instances=instances, **kwargs)


class ResumeUpdatePolicy(SimpleCreateMixin, SimpleStartMixin, SimpleRestartMixin, SimpleStopMixin, SimpleRemoveMixin,
                         ResumeStartupMixin, SimpleShutdownMixin, ContainerUpdateMixin, ScriptMixin, BasePolicy):
    pass
