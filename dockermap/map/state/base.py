# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
from abc import abstractmethod
import logging

from six import with_metaclass

from ...utils import format_image_tag
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
    :param config_flags: Config flags on the container.
    :type config_flags: int
    """
    def __init__(self, policy, options, client_name, config_id, config_flags=ConfigFlags.NONE, *args, **kwargs):
        self.policy = policy
        self.options = options
        self.client_name = client_name
        self.client_config = client_config = self.policy.clients[client_name]
        self.client = client_config.get_client()
        self.config_id = config_id
        self.config_flags = config_flags
        self.container_map = policy.container_maps[config_id.map_name]
        self.config = None
        self.detail = None

    def set_defaults(self):
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
    :param config_flags: Config flags on the container.
    :type config_flags: int
    """
    def __init__(self, *args, **kwargs):
        super(ContainerBaseState, self).__init__(*args, **kwargs)
        self.config = config = self.container_map.get_existing(self.config_id.config_name)
        if not config:
            raise KeyError("Container configuration '{0.config_name}' not found on map '{0.map_name}'."
                           "".format(self.config_id))
        self.container_name = None

    def set_defaults(self):
        super(ContainerBaseState, self).set_defaults()
        self.container_name = None

    def inspect(self):
        """
        Fetches information about the container from the client.
        """
        policy = self.policy
        config_id = self.config_id
        if self.config_id.config_type == ItemType.VOLUME:
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

        extra_data = {
            'id': c_detail['Id']
        }
        c_status = c_detail['State']
        if c_status['Running']:
            base_state = State.RUNNING
            state_flag = StateFlags.NONE
            extra_data['pid'] = c_status['Pid']
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
        if self.config.persistent:
            state_flag |= StateFlags.PERSISTENT
        force_update = self.options['force_update']
        if force_update and self.config_id in force_update:
            state_flag |= StateFlags.FORCED_RESET
        return base_state, state_flag, extra_data


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
    :param config_flags: Config flags on the container.
    :type config_flags: int
    """
    def __init__(self, *args, **kwargs):
        super(NetworkBaseState, self).__init__(*args, **kwargs)
        self.config = config = self.container_map.get_existing_network(self.config_id.config_name)
        if not config:
            raise KeyError("Network configuration '{0.config_name}' not found on map '{0.map_name}'."
                           "".format(self.config_id))
        self.network_name = None

    def set_defaults(self):
        super(NetworkBaseState, self).set_defaults()
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
        n_detail = self.detail
        n_id = n_detail['Id']
        connected_containers = n_detail.get('Containers', {})
        force_update = self.options['force_update']
        if force_update and self.config_id in force_update:
            state_flag = StateFlags.FORCED_RESET
        else:
            state_flag = StateFlags.NONE
        return State.PRESENT, state_flag, {'id': n_id, 'containers': connected_containers}


class VolumeBaseState(AbstractState):
    """
    Base implementation for determining the current state of a single volume on the client.

    :param policy: Policy object.
    :type policy: dockermap.map.policy.base.BasePolicy
    :param options: Dictionary of options passed to the state generator.
    :type options: dict
    :param client_name: Client name.
    :type client_name: unicode | str
    :param config_id: Configuration id tuple.
    :type config_id: dockermap.map.input.MapConfigId
    :param config_flags: Config flags on the container.
    :type config_flags: int
    """
    def __init__(self, *args, **kwargs):
        super(VolumeBaseState, self).__init__(*args, **kwargs)
        self.config = self.container_map.get_existing_volume(self.config_id.instance_name)
        self.volume_name = None

    def set_defaults(self):
        super(VolumeBaseState, self).set_defaults()
        self.volume_name = None

    def inspect(self):
        """
        Inspects the network state.
        """
        if not self.client_config.supports_volumes:
            raise ValueError("Client does not support volume configuration.", self.client_name)
        config_id = self.config_id
        parent_name = config_id.config_name if self.container_map.use_attached_parent_name else None
        volume_name = self.volume_name = self.policy.aname(config_id.map_name, config_id.instance_name,
                                                           parent_name=parent_name)
        if volume_name in self.policy.volume_names[self.client_name]:
            self.detail = self.client.inspect_volume(volume_name)
        else:
            self.detail = NOT_FOUND

    def get_state(self):
        if self.detail is NOT_FOUND:
            return State.ABSENT, StateFlags.NONE, {}
        force_update = self.options['force_update']
        if force_update and self.config_id in force_update:
            state_flag = StateFlags.FORCED_RESET
        else:
            state_flag = StateFlags.NONE
        return State.PRESENT, state_flag, {}


class ImageBaseState(AbstractState):
    """
    Base implementation for determining the current state of an image. There is no configuration object passed to
    this inspection. The image name is represented in the ``config_name`` of the configuration id, and the tag in
    ``instance_name``.
    """
    def inspect(self):
        """
        Fetches image information from the client.
        """
        policy = self.policy
        image_name = format_image_tag((self.config_id.config_name, self.config_id.instance_name))
        image_id = policy.images[self.client_name].get(image_name)
        if image_id:
            self.detail = {'Id': image_id}   # Currently there is no need for actually inspecting the image.
        else:
            self.detail = NOT_FOUND

    def get_state(self):
        i_detail = self.detail
        if i_detail is NOT_FOUND:
            return State.ABSENT, StateFlags.NONE, {}
        i_id = i_detail['Id']
        return State.PRESENT, StateFlags.NONE, {'id': i_id}


class AbstractStateGenerator(with_metaclass(ABCPolicyUtilMeta, PolicyUtil)):
    """
    Abstract base implementation for an state generator, which determines the current state of containers on the client.
    """
    container_state_class = ContainerBaseState
    network_state_class = NetworkBaseState
    volume_state_class = VolumeBaseState
    image_state_class = ImageBaseState

    nonrecoverable_exit_codes = (-127, -1)
    force_update = None
    policy_options = ['nonrecoverable_exit_codes', 'force_update']

    def get_container_state(self, *args, **kwargs):
        return self.container_state_class(self._policy, self.get_options(), *args, **kwargs)

    def get_network_state(self, *args, **kwargs):
        return self.network_state_class(self._policy, self.get_options(), *args, **kwargs)

    def get_volume_state(self, *args, **kwargs):
        return self.volume_state_class(self._policy, self.get_options(), *args, **kwargs)

    def get_image_state(self, *args, **kwargs):
        return self.image_state_class(self._policy, self.get_options(), *args, **kwargs)

    def generate_config_states(self, config_id, config_flags=ConfigFlags.NONE):
        """
        Generates the actions on a single item, which can be either a dependency or a explicitly selected
        container.

        :param config_id: Configuration id tuple.
        :type config_id: dockermap.map.input.MapConfigId
        :param config_flags: Optional configuration flags.
        :type config_flags: dockermap.map.policy.ConfigFlags
        :return: Generator for container state information.
        :rtype: collections.Iterable[dockermap.map.state.ContainerConfigStates]
        """
        c_map = self._policy.container_maps[config_id.map_name]
        clients = c_map.clients or [self._policy.default_client_name]
        config_type = config_id.config_type

        for client_name in clients:
            if config_type == ItemType.CONTAINER:
                c_state = self.get_container_state(client_name, config_id, config_flags)
            elif config_type == ItemType.VOLUME:
                client_config = self._policy.clients[client_name]
                if client_config.supports_volumes:
                    c_state = self.get_volume_state(client_name, config_id, config_flags)
                else:
                    c_state = self.get_container_state(client_name, config_id, config_flags)
            elif config_type == ItemType.NETWORK:
                c_state = self.get_network_state(client_name, config_id, config_flags)
            elif config_type == ItemType.IMAGE:
                c_state = self.get_image_state(client_name, config_id, config_flags)
            else:
                raise ValueError("Invalid configuration type.", config_type)
            c_state.inspect()
            # Extract base state, state flags, and extra info.
            state_info = ConfigState(client_name, config_id, config_flags, *c_state.get_state())
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
            for state in self.generate_config_states(d_config_id, config_flags=ConfigFlags.DEPENDENT):
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


class ImageDependencyStateGenerator(AbstractDependencyStateGenerator):
    def get_dependency_path(self, config_id):
        return [d for d in self._policy.get_dependencies(config_id) if d.config_type == ItemType.IMAGE]


class DependentStateGenerator(AbstractDependencyStateGenerator):
    def get_dependency_path(self, config_id):
        return self._policy.get_dependents(config_id)
