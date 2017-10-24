# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import sys

import docker

from ..exceptions import PartialResultsError
from .action import simple, script, update
from .config.client import ClientConfiguration
from .config.main import ContainerMap
from .config.utils import get_map_config_ids
from .exceptions import ActionException, ActionRunnerException
from .policy.base import BasePolicy
from .runner.base import DockerClientRunner
from .state.base import (SingleStateGenerator, DependencyStateGenerator, DependentStateGenerator,
                         ImageDependencyStateGenerator)
from .state.update import UpdateStateGenerator


log = logging.getLogger(__name__)


def _set_forced_update_ids(kwargs, maps, default_map_name, default_instances):
    value = kwargs.pop('force_update', None)
    if not value:
        return
    config_ids = get_map_config_ids(value, maps, default_map_name, default_instances)
    if config_ids:
        kwargs['force_update'] = set(config_ids)


class MappingDockerClient(object):
    """
    Reflects a :class:`~dockermap.map.config.main.ContainerMap` instance on a Docker client
    (:class:`~docker.client.Client` or a subclass, e.g. :class:`~dockermap.map.base.DockerClientWrapper`).
    The ``policy_class`` determines if and how dependencies are being considered during creation, starting, stopping,
    and removal of containers.

    If only one container map is provided, it will be the default map for all operations. If multiple container maps
    are used, the list can contain instances of clients to be used. In that case, the ``docker_client`` argument is
    ignored.

    Image names, container status, and dependencies are cached. In order to force a refresh, use :meth:`refresh_names`.
    It is also cleared on every change of ``policy_class``.

    :param container_maps: :class:`~dockermap.map.config.main.ContainerMap` instance or a tuple or list of such
      instances along with an associated instance.
    :type container_maps: dockermap.map.config.main.ContainerMap or
      list[dockermap.map.config.main.ContainerMap] | dict[unicode | str, dockermap.map.config.main.ContainerMap]
    :param docker_client: Default :class:`~docker.client.Client` instance or configuration.
    :type docker_client: dockermap.map.config.client.ClientConfiguration or docker.client.Client
    :param clients: Dictionary of client configurations
    :type clients: dict[unicode | str, dockermap.map.config.client.ClientConfiguration]
    """
    configuration_class = ClientConfiguration
    policy_class = BasePolicy
    generators = {
        'create': (DependencyStateGenerator, simple.CreateActionGenerator),
        'start': (DependencyStateGenerator, simple.StartActionGenerator),
        'restart': (SingleStateGenerator, simple.RestartActionGenerator),
        'stop': (DependentStateGenerator, simple.StopActionGenerator),
        'remove': (DependentStateGenerator, simple.RemoveActionGenerator),
        'startup': (DependencyStateGenerator, simple.StartupActionGenerator),
        'shutdown': (DependentStateGenerator, simple.ShutdownActionGenerator),
        'update': (UpdateStateGenerator, update.UpdateActionGenerator),
        'script': (DependencyStateGenerator, script.ScriptActionGenerator),
        'signal': (SingleStateGenerator, simple.SignalActionGenerator),
        'pull_images': (ImageDependencyStateGenerator, simple.ImagePullActionGenerator),
    }
    runner_class = DockerClientRunner

    def __init__(self, container_maps=None, docker_client=None, clients=None):
        if container_maps:
            if isinstance(container_maps, ContainerMap):
                self._default_map = container_maps.name
                self._maps = {container_maps.name: container_maps}
            elif isinstance(container_maps, (list, tuple)):
                self._default_map = None
                self._maps = {c_map.name: c_map for c_map in container_maps}
            elif isinstance(container_maps, dict):
                self._default_map = None
                self._maps = container_maps
            else:
                raise ValueError("Unexpected type of 'container_maps' argument: {0}".format(type(container_maps).__name__))
        else:
            self._default_map = None
            self._maps = {}
        if clients and isinstance(clients, (list, tuple)):
            self._clients = dict(clients)
        else:
            self._clients = clients or {}

        if docker_client is not None:
            if isinstance(docker_client, ClientConfiguration):
                default_client = docker_client
            else:
                default_client = self.configuration_class.from_client(docker_client)
            self._clients[self.policy_class.default_client_name] = default_client
        self._policy = None

    def get_policy(self):
        """
        Returns an instance of :attr:`~policy_class`.

        :return: An instance of the current policy class.
        :rtype: dockermap.map.policy.base.BasePolicy
        """
        if not self._policy:
            self._policy = self.policy_class(self._maps, self._clients)
        return self._policy

    def get_state_generator(self, action_name, policy, kwargs):
        """
        Returns the state generator to be used for the given action.

        :param action_name: Action identifier name.
        :type action_name: unicode | str
        :param policy: An instance of the current policy class.
        :type policy: dockermap.map.policy.base.BasePolicy
        :param kwargs: Keyword arguments. Can be modified by the initialization of the state generator.
        :type kwargs: dict
        :return: State generator object.
        :rtype: dockermap.map.state.base.AbstractStateGenerator
        """
        state_generator_cls = self.generators[action_name][0]
        state_generator = state_generator_cls(policy, kwargs)
        return state_generator

    def get_action_generator(self, action_name, policy, kwargs):
        """
        Returns the action generator to be used for the given action.

        :param action_name: Action identifier name.
        :type action_name: unicode | str
        :param policy: An instance of the current policy class.
        :type policy: dockermap.map.policy.base.BasePolicy
        :param kwargs: Keyword arguments. Can be modified by the initialization of the action generator.
        :type kwargs: dict
        :return: Action generator object.
        :rtype: dockermap.map.action.base.AbstractActionGenerator
        """
        action_generator_cls = self.generators[action_name][1]
        action_generator = action_generator_cls(policy, kwargs)
        return action_generator

    def get_runner(self, policy, kwargs):
        """
        Returns a runner for running actions.

        :param policy: An instance of the current policy class.
        :type policy: dockermap.map.policy.base.BasePolicy
        :param kwargs: Keyword arguments. Can be modified by the initialization of the runner.
        :type kwargs: dict
        :return: Runner instance.
        :rtype: dockermap.map.runner.AbstractRunner
        """
        return self.runner_class(policy, kwargs)

    def get_states(self, action_name, config_name, instances=None, map_name=None, **kwargs):
        """
        Returns a generator of states in relation to the indicated action.

        :param action_name: Action name.
        :type action_name: unicode | str
        :param config_name: Name(s) of container configuration(s) or MapConfigId tuple(s).
        :type config_name: unicode | str | collections.Iterable[unicode | str] | dockermap.map.input.InputConfigId | collections.Iterable[dockermap.map.input.InputConfigId]
        :param instances: Optional instance names, where applicable but not included in ``config_name``.
        :type instances: unicode | str | collections.Iterable[unicode | str]
        :param map_name: Optional map name, where not inlcuded in ``config_name``.
        :param kwargs: Additional kwargs for state generation, action generation, runner, or the client action.
        :return: Resulting states of the configurations.
        :rtype: collections.Iterable[dockermap.map.state.ConfigState]
        """
        policy = self.get_policy()
        _set_forced_update_ids(kwargs, policy.container_maps, map_name or self._default_map, instances)
        state_generator = self.get_state_generator(action_name, policy, kwargs)
        log.debug("Remaining kwargs passed to client actions: %s", kwargs)
        config_ids = get_map_config_ids(config_name, policy.container_maps, map_name or self._default_map,
                                        instances)
        log.debug("Generating states for configurations: %s", config_ids)
        return state_generator.get_states(config_ids)

    def get_actions(self, action_name, config_name, instances=None, map_name=None, **kwargs):
        """
        Returns the entire set of actions performed for the indicated action name.

        :param action_name: Action name.
        :type action_name: unicode | str
        :param config_name: Name(s) of container configuration(s) or MapConfigId tuple(s).
        :type config_name: unicode | str | collections.Iterable[unicode | str] | dockermap.map.input.MapConfigId | collections.Iterable[dockermap.map.input.MapConfigId]
        :param instances: Optional instance names, where applicable but not included in ``config_name``.
        :type instances: unicode | str | collections.Iterable[unicode | str]
        :param map_name: Optional map name, where not inlcuded in ``config_name``.
        :param kwargs: Additional kwargs for state generation, action generation, runner, or the client action.
        :return: Resulting actions of the configurations.
        :rtype: collections.Iterable[list[dockermap.map.action.ItemAction]]
        """
        policy = self.get_policy()
        action_generator = self.get_action_generator(action_name, policy, kwargs)
        for state in self.get_states(action_name, config_name, instances=instances, map_name=map_name, **kwargs):
            log.debug("Evaluating state: %s.", state)
            actions = action_generator.get_state_actions(state, **kwargs)
            if actions:
                log.debug("Running actions: %s", actions)
                yield actions
            else:
                log.debug("No actions returned.")

    def run_actions(self, action_name, config_name, instances=None, map_name=None, **kwargs):
        """
        Runs the entire set of actions performed for the indicated action name. On any client failure this raises a
        :class:`~dockermap.map.exceptions.ActionRunnerException`, where partial results can be reviewed in the property
        ``results``, or :class:`~dockermap.exceptions.MiscInvocationError` if no particular action was performed.

        :param action_name: Action name.
        :type action_name: unicode | str
        :param config_name: Name(s) of container configuration(s) or MapConfigId tuple(s).
        :type config_name: unicode | str | collections.Iterable[unicode | str] | dockermap.map.input.MapConfigId | collections.Iterable[dockermap.map.input.MapConfigId]
        :param instances: Optional instance names, where applicable but not included in ``config_name``.
        :type instances: unicode | str | collections.Iterable[unicode | str]
        :param map_name: Optional map name, where not inlcuded in ``config_name``.
        :param kwargs: Additional kwargs for state generation, action generation, runner, or the client action.
        :return: Client output of actions of the configurations.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        policy = self.get_policy()
        results = []
        runner = self.get_runner(policy, kwargs)
        for action_list in self.get_actions(action_name, config_name, instances, map_name, **kwargs):
            try:
                for res in runner.run_actions(action_list):
                    results.append(res)
            except ActionException as ae:
                raise ActionRunnerException.from_action_exception(ae, results)
            except:
                exc_info = sys.exc_info()
                raise PartialResultsError(exc_info, results)
        return results

    def create(self, container, instances=None, map_name=None, **kwargs):
        """
        Creates container instances for a container configuration.

        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance name to create. If not specified, will create all instances as specified in the
         configuration (or just one default instance).
        :type instances: tuple | list
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container creation.
        :return: Return values of created containers.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('create', container, instances=instances, map_name=map_name, **kwargs)

    def start(self, container, instances=None, map_name=None, **kwargs):
        """
        Starts instances for a container configuration.

        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance names to start. If not specified, will start all instances as specified in the
         configuration (or just one default instance).
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :type instances: collections.Iterable[unicode | str | NoneType]
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container start.
        :return: Return values of started containers.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('start', container, instances=instances, map_name=map_name, **kwargs)

    def restart(self, container, instances=None, map_name=None, **kwargs):
        """
        Restarts instances for a container configuration.

        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance names to stop. If not specified, will restart all instances as specified in the
         configuration (or just one default instance).
        :type instances: collections.Iterable[unicode | str | NoneType]
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container restart.
        :return: Return values of restarted containers.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('restart', container, instances=instances, map_name=map_name, **kwargs)

    def stop(self, container, instances=None, map_name=None, **kwargs):
        """
        Stops instances for a container configuration.

        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance names to stop. If not specified, will stop all instances as specified in the
         configuration (or just one default instance).
        :type instances: collections.Iterable[unicode | str | NoneType]
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored on stop and removal.
        :type raise_on_error: bool
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container stop.
        :return: Return values of stopped containers.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('stop', container, instances=instances, map_name=map_name, **kwargs)

    def remove(self, container, instances=None, map_name=None, **kwargs):
        """
        Remove instances from a container configuration.

        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: collections.Iterable[unicode | str | NoneType]
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container removal.
        :return: Return values of removed containers.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('remove', container, instances=instances, map_name=map_name, **kwargs)

    def startup(self, container, instances=None, map_name=None, **kwargs):
        """
        Start up container instances from a container configuration. Typically this means creating and starting
        containers and their dependencies. Note that not all policy classes necessarily implement this method.

        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: collections.Iterable[unicode | str | NoneType]
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :param kwargs: Additional kwargs. Only options controlling policy behavior are considered.
        :return: Return values of created containers.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('startup', container, instances=instances, map_name=map_name, **kwargs)

    def shutdown(self, container, instances=None, map_name=None, **kwargs):
        """
        Shut down container instances from a container configuration. Typically this means stopping and removing
        containers. Note that not all policy classes necessarily implement this method.

        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: collections.Iterable[unicode | str | NoneType]
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :param kwargs: Additional kwargs. Only options controlling policy behavior are considered.
        :return: Return values of removed containers.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('shutdown', container, instances=instances, map_name=map_name, **kwargs)

    def update(self, container, instances=None, map_name=None, **kwargs):
        """
        Updates instances from a container configuration. Typically this means restarting or recreating containers based
        on detected changes in the configuration or environment.  Note that not all policy classes necessarily implement
        this method.

        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: collections.Iterable[unicode | str | NoneType]
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :param kwargs: Additional kwargs. Only options controlling policy behavior are considered.
        :return: Return values of actions.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('update', container, instances=instances, map_name=map_name, **kwargs)

    def call(self, action_name, container, instances=None, map_name=None, **kwargs):
        """
        Generic function for running container actions based on a policy.

        :param action_name: Action name.
        :type action_name: unicode | str
        :param container: Container name.
        :type container: unicode | str
        :param instances: Instance names to remove. If not specified, runs on all instances as specified in the
         configuration (or just one default instance).
        :type instances: collections.Iterable[unicode | str | NoneType]
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode | str
        :param kwargs: Additional kwargs for the policy method.
        :return: Return values of actions.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions(action_name, container, instances=instances, map_name=map_name, **kwargs)

    def run_script(self, container, instance=None, map_name=None, **kwargs):
        """
        Runs a script or single command in the context of a container. By the default implementation this means creating
        the container along with all of its dependencies, mounting the script path, and running the script. The result
        is recorded in a dictionary per client, before the container is removed. Dependencies are not removed. For
        details, see :meth:`dockermap.map.runner.script.ScriptMixin.run_script`.

        :param container: Container configuration name.
        :type container: unicode | str
        :param map_name: Container map name.
        :type map_name: unicode | str
        :param instance: Instance name. Optional, if not specified runs the default instance.
        :type instance: unicode | str
        :param kwargs: Keyword arguments to the script runner function.
        :return: Return values of the script actions with their log output and exit codes.
        :return: A dictionary of client names with their log output and exit codes.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('script', container, instances=instance, map_name=map_name, **kwargs)

    def signal(self, container, instances=None, map_name=None, **kwargs):
        """
        Sends a signal to a single running container configuration (but possibly multiple instances). If not specified
        with ``signal``, this signal is ``SIGKILL``.

        :param container: Container configuration name.
        :type container: unicode | str
        :param map_name: Container map name.
        :type map_name: unicode | str
        :param instances: Instance name. Optional, if not specified sends the signal to all configured instances, or
          the default.
        :type instances: unicode | str
        :param kwargs: Keyword arguments to the script runner function.
        :return: Return values of actions.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('signal', container, instances=instances, map_name=map_name, **kwargs)

    def pull_images(self, container, instances=None, map_name=None, **kwargs):
        """
        Pulls images for container configurations along their dependency path.

        :param container: Container configuration name.
        :type container: unicode | str
        :param map_name: Container map name.
        :type map_name: unicode | str
        :param instances: Not applicable for images.
        :type instances: unicode | str
        :param kwargs: Keyword arguments to the script runner function.
        :return: Return values of actions.
        :rtype: list[dockermap.map.runner.ActionOutput]
        """
        return self.run_actions('pull_images', container, map_name=map_name, **kwargs)

    def refresh_names(self):
        """
        Invalidates the policy name and status cache.
        """
        self._policy = None

    def list_persistent_containers(self, map_name=None):
        """
        Lists the names of all persistent containers on the specified map or all maps. Attached containers are always
        considered persistent.

        :param map_name: Container map name. Optional, only returns persistent containers from the specified map.
        :type map_name: unicode | str
        :return: List of container names.
        :rtype: list[unicode | str]
        """
        if map_name:
            maps = [self._maps[map_name].get_extended_map()]
        else:
            maps = [m.get_extended_map() for m in self._maps.values()]
        cname_func = self.policy_class.cname
        aname_func = self.policy_class.aname
        c_names = []
        for c_map in maps:
            m_name = c_map.name
            attached, persistent = c_map.get_persistent_items()
            if c_map.use_attached_parent_name:
                c_names.extend([aname_func(m_name, ca, c_name)
                                for c_name, ca in attached])
            else:
                c_names.extend([aname_func(m_name, ca[1])
                                for ca in attached])
            c_names.extend([cname_func(m_name, c_name, ci)
                            for c_name, ci in persistent])
        return c_names

    @property
    def maps(self):
        """
        Container maps.

        :return: A dictionary with container map names as keys, and the container maps values.
        :rtype: dict[unicode | str, dockermap.map.config.main.ContainerMap]
        """
        return self._maps

    @property
    def clients(self):
        """
        Clients and their configuration objects.

        :return: Dictionary of client names, with their client instance and a configuration object as values.
        :rtype: dict[unicode | str, dockermap.map.config.client.ClientConfiguration]
        """
        return self._clients

    @property
    def default_map(self):
        """
        The default map to use for any actions, if not otherwise specified.

        :return: Container map name.
        :rtype: unicode | str
        """
        return self._default_map

    @default_map.setter
    def default_map(self, value):
        if value not in self._maps:
            raise ValueError("Default name must match an available map name.")
        self._default_map = value
