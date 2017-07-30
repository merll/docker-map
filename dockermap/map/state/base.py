# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
from abc import abstractmethod
import logging

from six import with_metaclass

from ..input import ItemType
from ..policy import ConfigFlags, ABCPolicyUtilMeta, PolicyUtil
from . import INITIAL_START_TIME, State, StateFlags, ConfigState
from .utils import merge_dependency_paths


log = logging.getLogger(__name__)


class _ObjectNotFound(object):
    def __nonzero__(self):
        return False

    __bool__ = __nonzero__


NOT_FOUND = _ObjectNotFound()


class AbstractState(object):
    """
    Abstract base implementation for determining the current state of a single object on the client.

    :param policy: Policy object.
    :type policy: dockermap.map.policy.base.BasePolicy
    :param options: Dictionary of options passed to the state generator.
    :type options: dict
    :param client_name: Client name.
    :type client_name: unicode | str
    :param config_id: Configuration id tuple.
    :type config_id: dockermap.map.input.MapConfigId
    :param container_map: Container map instance.
    :type container_map: dockermap.map.config.main.ContainerMap
    :param config: Configuration object.
    :param config_flags: Config flags on the container.
    :type config_flags: int
    """
    def __init__(self, policy, options, client_name, config_id, container_map, config, config_flags=ConfigFlags.NONE,
                 *args, **kwargs):
        self.policy = policy
        self.options = options
        self.config_id = config_id
        self.container_map = container_map
        self.client_name = client_name
        self.client_config = client_config = policy.clients[client_name]
        self.client = client_config.get_client()
        self.config = config
        self.config_flags = config_flags
        self.detail = None

    def set_defaults(self, *args, **kwargs):
        """
        Resets the state, so that with adjustments of input parameters the object can be reused without side-effects
        to other objects on the client.
        """
        self.detail = None

    def inspect(self):
        """
        Inspects the object on the client, i.e. makes actual calls to the client to check on the object.
        """
        pass

    def get_state(self):
        """
        Determines and returns the state information.

        :return: State information.
        :type: tuple
        """
        pass


class ContainerBaseState(AbstractState):
    """
    Base implementation for determining the current state of a single container on the client.

    :param policy: Policy object.
    :type policy: dockermap.map.policy.base.BasePolicy
    :param options: Dictionary of options passed to the state generator.
    :type options: dict
    :param client_name: Client name.
    :type client_name: unicode | str
    :param config_id: Configuration id tuple.
    :type config_id: dockermap.map.input.MapConfigId
    :param container_map: Container map instance.
    :type container_map: dockermap.map.config.main.ContainerMap
    :param config: Container configuration object.
    :type config: dockermap.map.config.container.ContainerConfiguration
    :param config_flags: Config flags on the container.
    :type config_flags: int
    """
    def __init__(self, *args, **kwargs):
        super(ContainerBaseState, self).__init__(*args, **kwargs)
        self.container_name = None

    def set_defaults(self, *args, **kwargs):
        super(ContainerBaseState, self).set_defaults(*args, **kwargs)
        self.container_name = None

    def inspect(self):
        """
        Fetches information about the container from the client.
        """
        super(ContainerBaseState, self).inspect()
        policy = self.policy
        config_id = self.config_id
        if self.config_flags & ConfigFlags.CONTAINER_ATTACHED:
            if self.container_map.use_attached_parent_name:
                container_name = policy.aname(config_id.map_name, config_id.instance_name, config_id.config_name)
            else:
                container_name = policy.aname(config_id.map_name, config_id.instance_name)
        else:
            container_name = policy.cname(config_id.map_name, config_id.config_name, config_id.instance_name)

        self.container_name = container_name
        if container_name in policy.container_names[self.client_name]:
            self.detail = self.client.inspect_container(container_name)
        else:
            self.detail = NOT_FOUND

    def get_state(self):
        c_detail = self.detail
        if c_detail is NOT_FOUND:
            return State.ABSENT, StateFlags.NONE, {}

        c_status = c_detail['State']
        if c_status['Running']:
            base_state = State.RUNNING
            state_flag = StateFlags.NONE
        else:
            base_state = State.PRESENT
            if c_status['StartedAt'] == INITIAL_START_TIME:
                state_flag = StateFlags.INITIAL
            elif c_status['ExitCode'] in self.options['nonrecoverable_exit_codes']:
                state_flag = StateFlags.NONRECOVERABLE
            else:
                state_flag = StateFlags.NONE
            if c_status['Restarting']:
                state_flag |= StateFlags.RESTARTING
        force_update = self.options['force_update']
        if force_update and self.config_id in force_update:
            state_flag |= StateFlags.FORCED_RESET
        return base_state, state_flag, {}


class NetworkBaseState(AbstractState):
    """
    Base implementation for determining the current state of a single network on the client.

    :param policy: Policy object.
    :type policy: dockermap.map.policy.base.BasePolicy
    :param options: Dictionary of options passed to the state generator.
    :type options: dict
    :param client_name: Client name.
    :type client_name: unicode | str
    :param config_id: Configuration id tuple.
    :type config_id: dockermap.map.input.MapConfigId
    :param container_map: Container map instance.
    :type container_map: dockermap.map.config.main.ContainerMap
    :param config: Network configuration object.
    :type config: dockermap.map.config.network.NetworkConfiguration
    :param config_flags: Config flags on the container.
    :type config_flags: int
    """
    def __init__(self, *args, **kwargs):
        super(NetworkBaseState, self).__init__(*args, **kwargs)
        self.network_name = None

    def set_defaults(self, *args, **kwargs):
        self.network_name = None

    def inspect(self):
        """
        Inspects the network state.
        """
        if not self.client_config.supports_networks:
            raise ValueError("Client does not support network configuration.", self.client_name)
        config_id = self.config_id
        network_name = self.network_name = self.policy.nname(config_id.map_name, config_id.config_name)
        if network_name in self.policy.network_names[self.client_name]:
            self.detail = self.client.inspect_network(network_name)
        else:
            self.detail = NOT_FOUND

    def get_state(self):
        if self.detail is NOT_FOUND:
            return State.ABSENT, StateFlags.NONE, {}
        connected_containers = self.detail.get('Containers', {})
        force_update = self.options['force_update']
        if force_update and self.config_id in force_update:
            state_flag = StateFlags.FORCED_RESET
        else:
            state_flag = StateFlags.NONE
        return State.PRESENT, state_flag, {'containers': connected_containers}


class AbstractStateGenerator(with_metaclass(ABCPolicyUtilMeta, PolicyUtil)):
    """
    Abstract base implementation for an state generator, which determines the current state of containers on the client.
    """
    container_state_class = ContainerBaseState
    network_state_class = NetworkBaseState

    nonrecoverable_exit_codes = (-127, -1)
    force_update = None
    policy_options = ['nonrecoverable_exit_codes', 'force_update']

    def get_container_state(self, *args, **kwargs):
        return self.container_state_class(self._policy, self.get_options(), *args, **kwargs)

    def get_network_state(self, *args, **kwargs):
        return self.network_state_class(self._policy, self.get_options(), *args, **kwargs)

    def generate_config_states(self, config_id, is_dependency=False):
        """
        Generates the actions on a single item, which can be either a dependency or a explicitly selected
        container.

        :param config_id: Configuration id tuple.
        :type config_id: dockermap.map.input.MapConfigId
        :param is_dependency: Whether the state check is on a dependency or dependent container.
        :type is_dependency: bool
        :return: Generator for container state information.
        :rtype: collections.Iterable[dockermap.map.state.ContainerConfigStates]
        """
        c_map = self._policy.container_maps[config_id.map_name]
        c_flags = ConfigFlags.DEPENDENT if is_dependency else ConfigFlags.NONE
        config_type = config_id.config_type
        config_name = config_id.config_name

        if config_type == ItemType.CONTAINER:
            config = c_map.get_existing(config_name)
            if not config:
                raise KeyError("Container configuration '{0.config_name}' not found on map '{0.map_name}'."
                               "".format(config_id))
            clients = self._policy.get_clients(c_map, config)
            if config.persistent:
                c_flags |= ConfigFlags.CONTAINER_PERSISTENT
            state_func = self.get_container_state
        elif config_type == ItemType.VOLUME:
            config = c_map.get_existing(config_name)
            if not config:
                raise KeyError("Container configuration '{0.config_name}' not found on map '{0.map_name}'."
                               "".format(config_id))
            clients = self._policy.get_clients(c_map, config)
            # TODO: Change for actual volumes.
            c_flags |= ConfigFlags.CONTAINER_ATTACHED
            state_func = self.get_container_state
        elif config_type == ItemType.NETWORK:
            config = c_map.get_existing_network(config_name)
            if not config:
                raise KeyError("Network configuration '{0.config_name}' not found on map '{0.map_name}'."
                               "".format(config_id))
            clients = self._policy.get_clients(c_map)
            state_func = self.get_network_state
        else:
            raise ValueError("Invalid configuration type.", config_type)

        for client_name in clients:
            c_state = state_func(client_name, config_id, c_map, config, c_flags)
            c_state.inspect()
            # Extract base state, state flags, and extra info.
            state_info = ConfigState(client_name, config_id, c_flags, *c_state.get_state())
            log.debug("Configuration state information: %s", state_info)
            yield state_info

    @abstractmethod
    def get_states(self, config_ids):
        """
        To be implemented by subclasses. Generates state information for the selected containers.

        :param config_ids: MapConfigId tuple.
        :type config_ids: list[dockermap.map.input.MapConfigId]
        :return: Iterable of configuration states.
        :rtype: collections.Iterable[dockermap.map.state.ConfigState]
        """
        pass

    @property
    def policy(self):
        """
        Policy object instance to generate actions for.

        :return: Policy object instance.
        :rtype: BasePolicy
        """
        return self._policy

    @policy.setter
    def policy(self, value):
        self._policy = value


class SingleStateGenerator(AbstractStateGenerator):
    def get_states(self, config_ids):
        """
        Generates state information for the selected containers.

        :param config_ids: List of MapConfigId tuples.
        :type config_ids: list[dockermap.map.input.MapConfigId]
        :return: Iterable of configuration states.
        :rtype: collections.Iterable[dockermap.map.state.ConfigState]
        """
        return itertools.chain.from_iterable(self.generate_config_states(config_id)
                                             for config_id in config_ids)


class AbstractDependencyStateGenerator(with_metaclass(ABCPolicyUtilMeta, AbstractStateGenerator)):
    @abstractmethod
    def get_dependency_path(self, config_id):
        """
        To be implemented by subclasses (or using :class:`ForwardActionGeneratorMixin` or
        :class:`ReverseActionGeneratorMixin`). Should provide an iterable of objects to be handled before the explicitly
        selected container configuration.

        :param config_id: MapConfigId tuple.
        :type config_id: dockermap.map.input.MapConfigId
        :return: Iterable of dependency objects in tuples of configuration type, map name, config name, and instance.
        :rtype: collections.Iterable[dockermap.map.input.MapConfigId]
        """
        pass

    def _get_all_states(self, config_id, dependency_path):
        log.debug("Following dependency path for %s.", config_id)
        for d_config_id in dependency_path:
            log.debug("Dependency path at %s.", d_config_id)
            for state in self.generate_config_states(d_config_id, is_dependency=True):
                yield state
        log.debug("Processing state for %s.", config_id)
        for state in self.generate_config_states(config_id):
            yield state

    def get_states(self, config_ids):
        """
        Generates state information for the selected container and its dependencies / dependents.

        :param config_ids: MapConfigId tuples.
        :type config_ids: list[dockermap.map.input.MapConfigId]
        :return: Iterable of configuration states.
        :rtype: collections.Iterable[dockermap.map.state.ConfigState]
        """
        input_paths = [
            (config_id, list(self.get_dependency_path(config_id)))
            for config_id in config_ids
        ]
        log.debug("Dependency paths from input: %s", input_paths)
        dependency_paths = merge_dependency_paths(input_paths)
        log.debug("Merged dependency paths: %s", dependency_paths)
        return itertools.chain.from_iterable(self._get_all_states(config_id, dependency_path)
                                             for config_id, dependency_path in dependency_paths)


class DependencyStateGenerator(AbstractDependencyStateGenerator):
    def get_dependency_path(self, config_id):
        return self._policy.get_dependencies(config_id)


class DependentStateGenerator(AbstractDependencyStateGenerator):
    def get_dependency_path(self, config_id):
        return self._policy.get_dependents(config_id)
