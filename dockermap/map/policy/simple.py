# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
from requests.exceptions import ReadTimeout

from .base import (BasePolicy, AttachedPreparationMixin, ExecMixin, ForwardActionGeneratorMixin,
                   AbstractActionGenerator, AbstractDependentActionGenerator, ReverseActionGeneratorMixin, SignalMixin)
from . import ACTION_DEPENDENCY_FLAG, utils


class SimpleCreateGenerator(ForwardActionGeneratorMixin, AbstractDependentActionGenerator):
    def generate_item_actions(self, map_name, c_map, config_name, c_config, instances, flags, *args, **kwargs):
        for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
            use_host_config = utils.use_host_config(client)
            existing_containers = self._policy.container_names[client_name]
            images = self._policy.images[client_name]
            a_parent = config_name if c_map.use_attached_parent_name else None
            for a in c_config.attaches:
                a_name = self._policy.aname(map_name, a, a_parent)
                if a_name not in existing_containers:
                    a_kwargs = self._policy.get_attached_create_kwargs(c_map, config_name, c_config, client_name,
                                                                       client_config, a_name, a,
                                                                       include_host_config=use_host_config)
                    images.ensure_image(a_kwargs['image'])
                    client.create_container(**a_kwargs)
                    existing_containers.add(a_name)
            for ci in instances:
                ci_name = self._policy.cname(map_name, config_name, ci)
                if ci_name not in existing_containers:
                    c_kwargs = self._policy.get_create_kwargs(c_map, config_name, c_config, client_name,
                                                              client_config, ci_name, ci,
                                                              include_host_config=use_host_config, kwargs=kwargs)
                    images.ensure_image(c_kwargs['image'])
                    yield client_name, client.create_container(**c_kwargs)
                    existing_containers.add(ci_name)


class SimpleCreateMixin(object):
    def create_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for creating any configured container that does not already exist, including all of its
        dependencies.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          created.
        :type instances: list[unicode | str]
        :param kwargs: Additional keyword args for the create action.
        :return: Return values of created main containers.
        :rtype: list[(unicode | str, dict)]
        """
        return SimpleCreateGenerator(self).get_all_actions(map_name, container, instances=instances, **kwargs)


class SimpleStartGenerator(AttachedPreparationMixin, ExecMixin, ForwardActionGeneratorMixin, AbstractDependentActionGenerator):
    def generate_item_actions(self, map_name, c_map, config_name, c_config, instances, flags, *args, **kwargs):
        for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
            use_host_config = utils.use_host_config(client)
            a_parent = config_name if c_map.use_attached_parent_name else None
            for a in c_config.attaches:
                a_name = self._policy.aname(map_name, a, a_parent)
                a_status = client.inspect_container(a_name)['State']
                if a_status['ExitCode'] != 0 or utils.is_initial(a_status):
                    if use_host_config:
                        a_kwargs = dict(container=a_name)
                    else:
                        a_kwargs = self._policy.get_attached_host_config_kwargs(c_map, config_name, c_config,
                                                                                client_name, client_config, a_name, a)
                    client.start(**a_kwargs)
                    self.prepare_container(c_map, config_name, c_config, client_name, client_config, client, a,
                                           a_name)
            for instance in instances:
                ci_name = self._policy.cname(map_name, config_name, instance)
                ci_status = client.inspect_container(ci_name)['State']
                if not ci_status['Running']:
                    if use_host_config:
                        c_kwargs = dict(container=ci_name)
                    else:
                        c_kwargs = self._policy.get_host_config_kwargs(c_map, config_name, c_config, client_name,
                                                                       client_config, ci_name, instance, kwargs=kwargs)
                    client.start(**c_kwargs)
                    self.exec_container_commands(c_map, config_name, c_config, client_name, client_config, client,
                                                 ci_name, instance, utils.is_initial(ci_status))


class SimpleStartMixin(object):
    def start_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for starting any configured container that is not running, including all of its dependencies.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          started.
        :type instances: list[unicode | str]
        :param kwargs: Additional keyword args for the start action.
        """
        SimpleStartGenerator(self).get_all_actions(map_name, container, instances=instances, **kwargs)


class SimpleRestartGenerator(ExecMixin, SignalMixin, AbstractActionGenerator):
    def generate_item_actions(self, map_name, c_map, config_name, c_config, instances, flags, *args, **kwargs):
        """
        Generates actions for restarting a configured container. Does not consider dependencies.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          restarted.
        :type instances: list[unicode | str]
        :param kwargs: Additional keyword args for the restart action.
        """
        for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
            existing_containers = self._policy.container_names[client_name]
            for instance in instances:
                ci_name = self._policy.cname(map_name, config_name, instance)
                ci_status = client.inspect_container(ci_name)['State'] if ci_name in existing_containers else None
                if not utils.is_initial(ci_status):
                    if c_config.stop_signal:
                        try:
                            stop_timeout = kwargs.get('timeout')
                            if stop_timeout is not None:
                                stop_kwargs = {'timeout': stop_timeout}
                            else:
                                stop_kwargs = None
                            self.signal_stop(c_map, config_name, c_config, client_name, client_config, client, ci_name,
                                             instance, kwargs=stop_kwargs)
                        except ReadTimeout:
                            pass  # Restart will force it, or fail with a timeout as well.
                    c_kwargs = self._policy.get_restart_kwargs(c_map, config_name, c_config, client_name, client_config,
                                                               ci_name, instance, kwargs=kwargs)
                    client.restart(**c_kwargs)
                    self.exec_container_commands(c_map, config_name, c_config, client_name, client_config, client,
                                                 ci_name, instance, False)


class SimpleRestartMixin(ExecMixin, SignalMixin):
    def restart_actions(self, map_name, container, instances=None, **kwargs):
        SimpleRestartGenerator(self).generate_actions(map_name, container, instances, **kwargs)


class SimpleStopGenerator(ReverseActionGeneratorMixin, SignalMixin, AbstractDependentActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(SimpleStopGenerator, self).__init__(policy, *args, **kwargs)
        self._stop_dependent = policy.stop_dependent

    def generate_item_actions(self, map_name, c_map, config_name, c_config, instances, flags, *args, **kwargs):
        if self._stop_dependent or not flags & ACTION_DEPENDENCY_FLAG:
            for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
                existing_containers = self._policy.container_names[client_name]
                for instance in instances:
                    ci_name = self._policy.cname(map_name, config_name, instance)
                    ci_status = client.inspect_container(ci_name)['State'] if ci_name in existing_containers else None
                    if ci_status and not utils.is_initial(ci_status):
                        self.signal_stop(c_map, config_name, c_config, client_name, client_config, client, ci_name,
                                         instance, kwargs=kwargs)


class SimpleStopMixin(object):
    stop_dependent = True

    def stop_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for stopping any configured container that is running, including all of its
        dependents. Stopping dependent containers can be prevented by setting ``stop_dependent`` to ``False`` in
        subclasses.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          stopped.
        :type instances: list[unicode | str]
        :param kwargs: Additional keyword args for the stop action.
        """
        SimpleStopGenerator(self).get_all_actions(map_name, container, instances=instances, **kwargs)


class SimpleRemoveGenerator(ReverseActionGeneratorMixin, AbstractDependentActionGenerator):
    def __init__(self, policy, *args, **kwargs):
        super(SimpleRemoveGenerator, self).__init__(policy, *args, **kwargs)
        self._remove_dependent = policy.remove_dependent
        self._remove_persistent = policy.remove_persistent
        self._remove_attached = policy.remove_attached

    def generate_item_actions(self, map_name, c_map, config_name, c_config, instances, flags, *args, **kwargs):
        if ((self._remove_dependent or not flags & ACTION_DEPENDENCY_FLAG) and
                (self._remove_persistent or not c_config.persistent)):
            for client_name, client, client_config in self._policy.get_clients(c_config, c_map):
                existing_containers = self._policy.container_names[client_name]
                for instance in instances:
                    ci_name = self._policy.cname(map_name, config_name, instance)
                    if ci_name in existing_containers:
                        c_kwargs = self._policy.get_remove_kwargs(c_map, config_name, c_config, client_name,
                                                                  client_config, ci_name, kwargs=kwargs)
                        client.remove_container(**c_kwargs)
                        existing_containers.remove(ci_name)
                if self._remove_attached:
                    a_parent = config_name if c_map.use_attached_parent_name else None
                    for a in c_config.attaches:
                        a_name = self._policy.aname(map_name, a, a_parent)
                        if a_name in existing_containers:
                            a_kwargs = self._policy.get_remove_kwargs(c_map, config_name, c_config, client_name,
                                                                      client_config, a_name, kwargs=kwargs)
                            client.remove_container(**a_kwargs)
                            existing_containers.remove(a_name)


class SimpleRemoveMixin(object):
    remove_dependent = True
    remove_persistent = True
    remove_attached = False

    def remove_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for removing any configured container that exists, including all of its
        dependents. Removing dependent containers can be prevented by setting ``remove_dependent`` to ``False`` in
        subclasses. Containers with the :attr:`~dockermap.map.config.ContainerConfiguration.persistent` property are
        also removed, but attached containers are not.
        This behavior can be changed by setting ``remove_persistent`` and ``remove_attached`` in subclasses.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          removed.
        :type instances: list[unicode | str]
        :param kwargs: Additional keyword args for the remove action.
        """
        SimpleRemoveGenerator(self).get_all_actions(map_name, container, instances=instances, **kwargs)


class SimpleStartupMixin(object):
    def startup_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for creating any configured container that does not already exist, and start any non-running
        containers. This also applies to all of its dependencies.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          created and started.
        :type instances: list[unicode | str]
        :param kwargs: Has no effect in this implementation.
        :return: Return values of created main containers.
        :rtype: list[(unicode | str, dict)]
        """
        return itertools.chain(self.create_actions(map_name, container, instances) or (),
                               self.start_actions(map_name, container, instances) or ())


class SimpleShutdownMixin(object):
    def shutdown_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for stopping any configured container that is running, and removing any container that exists.
        This also applies to all of its dependent container configurations.

        Stopping dependent containers can be prevented by setting ``stop_dependent`` to ``False`` in
        subclasses. Removing dependent containers can be prevented by setting ``remove_dependent`` to ``False`` in
        subclasses. Containers with the :attr:`~dockermap.map.config.ContainerConfiguration.persistent` property are also
        removed, but attached containers are not. This behavior can be changed by setting ``remove_persistent`` and
        ``remove_attached`` in subclasses.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Optional, if ``None`` the configured instances or one default instance is
          stopped and removed.
        :type instances: list[unicode | str]
        :param kwargs: Has no effect in this implementation.
        """
        self.stop_actions(map_name, container, instances)
        self.remove_actions(map_name, container, instances)


class SimplePolicy(SimpleCreateMixin, SimpleStartMixin, SimpleRestartMixin, SimpleStopMixin, SimpleRemoveMixin,
                   SimpleStartupMixin, SimpleShutdownMixin, BasePolicy):
    pass
