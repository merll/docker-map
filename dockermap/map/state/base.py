# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
from abc import abstractmethod
import logging

from six import with_metaclass

from ..policy import (CONFIG_FLAG_DEPENDENT, CONFIG_FLAG_ATTACHED, CONFIG_FLAG_PERSISTENT,
                      ABCPolicyUtilMeta, PolicyUtil)
from . import (INITIAL_START_TIME, STATE_ABSENT, STATE_PRESENT, STATE_RUNNING, STATE_FLAG_INITIAL,
               STATE_FLAG_RESTARTING, STATE_FLAG_NONRECOVERABLE, STATE_FLAG_OUTDATED,
               ContainerConfigStates, ContainerInstanceState)
from .utils import merge_dependency_paths


log = logging.getLogger(__name__)


class AbstractStateGenerator(with_metaclass(ABCPolicyUtilMeta, PolicyUtil)):
    """
    Abstract base implementation for an state generator, which determines the current state of containers on the client.
    """
    nonrecoverable_exit_codes = (-127, -1)
    force_update = None
    policy_options = ['nonrecoverable_exit_codes', 'force_update']

    def get_container_state(self, map_name, container_map, config_name, container_config, client_name, client_config,
                            client, instance_alias, config_flags=0):
        """
        Fetches information about the container from the client and determines a base state. To be extended by
        subclasses as necessary.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container_map: Container map instance.
        :type container_map: dockermap.map.config.main.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.container.ContainerConfiguration
        :param client_name: Client name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.client.ClientConfiguration
        :param client: Docker client.
        :type client: docker.client.Client
        :param instance_alias: Container instance name or attached alias.
        :type instance_alias: unicode | str
        :param config_flags: Config flags on the container.
        :type config_flags: int
        :return: Tuple of container inspection detail, and the base state information derived from that.
        :rtype: (dict | NoneType, unicode | str, int, dict)
        """
        policy = self._policy
        if config_flags & CONFIG_FLAG_ATTACHED:
            if container_map.use_attached_parent_name:
                container_name = policy.aname(map_name, instance_alias, config_name)
            else:
                container_name = policy.aname(map_name, instance_alias)
        else:
            container_name = policy.cname(map_name, config_name, instance_alias)

        if container_name in policy.container_names[client_name]:
            c_detail = client.inspect_container(container_name)
            c_status = c_detail['State']
            if c_status['Running']:
                base_state = STATE_RUNNING
                state_flag = 0
            else:
                base_state = STATE_PRESENT
                if c_status['StartedAt'] == INITIAL_START_TIME:
                    state_flag = STATE_FLAG_INITIAL
                elif c_status['ExitCode'] in self.nonrecoverable_exit_codes:
                    state_flag = STATE_FLAG_NONRECOVERABLE
                else:
                    state_flag = 0
                if c_status['Restarting']:
                    state_flag |= STATE_FLAG_RESTARTING
            if self.force_update and (map_name, config_name, instance_alias) in self.force_update:
                state_flag |= STATE_FLAG_OUTDATED
            return c_detail, base_state, state_flag, {}
        return None, STATE_ABSENT, 0, {}

    def generate_config_states(self, map_name, config_name, instances, is_dependency=False):
        """
        Generates the actions on a single item, which can be either a dependency or a explicitly selected
        container.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param instances: Instance names as a list. Can be ``[None]``
        :type instances: list[unicode | str]
        :param is_dependency: Whether the state check is on a dependency or dependent container.
        :type is_dependency: bool
        :return: Generator for container state information.
        :rtype: collections.Iterable[dockermap.map.state.ContainerConfigStates]
        """
        c_map = self._policy.container_maps[map_name]
        c_config = c_map.get_existing(config_name)
        if not c_config:
            raise KeyError("Container configuration '{0}' not found on map '{1}'.".format(config_name, map_name))
        if is_dependency:
            if c_config.instances and len(instances) == 1 and instances[0] is None:
                c_instances = c_config.instances
            else:
                c_instances = instances or [None]
        else:
            c_instances = instances or c_config.instances or [None]

        config_flags = CONFIG_FLAG_DEPENDENT if is_dependency else 0
        a_flags = config_flags | CONFIG_FLAG_ATTACHED
        if c_config.persistent:
            config_flags |= CONFIG_FLAG_PERSISTENT
        clients = self._policy.get_clients(c_config, c_map)
        for client_name, client_config in clients:
            def _get_state(c_flags, items):
                for item in items:
                    state = self.get_container_state(map_name, c_map, config_name, c_config, client_name, client_config,
                                                     client, item, c_flags)
                    # Extract base state, state flags, and extra info.
                    yield ContainerInstanceState(item, state[1], state[2], state[3])

            client = client_config.get_client()
            attached_states = [a_state for a_state in _get_state(a_flags, c_config.attaches)]
            instance_states = [i_state for i_state in _get_state(config_flags, c_instances)]
            states = ContainerConfigStates(client_name, map_name, config_name, config_flags, instance_states,
                                           attached_states)
            log.debug("Container state information: %s", states)
            yield states

    @abstractmethod
    def get_states(self, config_ids):
        """
        To be implemented by subclasses. Generates state information for the selected containers.

        :param config_ids: MapConfigId tuple.
        :type config_ids: list[dockermap.map.input.MapConfigId]
        :return: Iterator over container configuration states.
        :rtype: collections.Iterable[dockermap.map.state.ContainerConfigStates]
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
        :return: Return values of created main containers.
        :rtype: collections.Iterable[dockermap.map.state.ContainerConfigStates]
        """
        return itertools.chain.from_iterable(self.generate_config_states(*config_id)
                                             for config_id in config_ids)


class AbstractDependencyStateGenerator(with_metaclass(ABCPolicyUtilMeta, AbstractStateGenerator)):
    @abstractmethod
    def get_dependency_path(self, map_name, config_name):
        """
        To be implemented by subclasses (or using :class:`ForwardActionGeneratorMixin` or
        :class:`ReverseActionGeneratorMixin`). Should provide an iterable of objects to be handled before the explicitly
        selected container configuration.

        :param map_name: Container map name.
        :param config_name: Container configuration name.
        :return: Iterable of dependency objects in tuples of map name, container (config) name, instances.
        :rtype: list[tuple]
        """
        pass

    def _get_all_states(self, config_id, dependency_path):
        log.debug("Following dependency path for %s.", config_id)
        for d_map_name, d_config_name, d_instances in dependency_path:
            log.debug("Dependency path at %s.%s, instances %s.", d_map_name, d_config_name, d_instances)
            for state in self.generate_config_states(d_map_name, d_config_name, d_instances, is_dependency=True):
                yield state
        log.debug("Processing state for %s.", config_id)
        for state in self.generate_config_states(*config_id):
            yield state

    def get_states(self, config_ids):
        """
        Generates state information for the selected container and its dependencies / dependents.

        :param config_ids: MapConfigId tuples.
        :type config_ids: list[dockermap.map.input.MapConfigId]
        :return: Return values of created main containers.
        :rtype: itertools.chain[dockermap.map.state.ContainerConfigStates]
        """
        input_paths = [
            (config_id, self.get_dependency_path(config_id.map_name, config_id.config_name))
            for config_id in config_ids
        ]
        log.debug("Dependency paths from input: %s", input_paths)
        dependency_paths = merge_dependency_paths(input_paths)
        log.debug("Merged dependency paths: %s", dependency_paths)
        return itertools.chain.from_iterable(self._get_all_states(config_id, dependency_path)
                                             for config_id, dependency_path in dependency_paths)


class DependencyStateGenerator(AbstractDependencyStateGenerator):
    def get_dependency_path(self, map_name, config_name):
        return [(map_name, config_name, tuple(instances))
                for map_name, config_name, instances in self._policy.get_dependencies(map_name, config_name)]


class DependentStateGenerator(AbstractDependencyStateGenerator):
    def get_dependency_path(self, map_name, config_name):
        return [(map_name, config_name, tuple(instances))
                for map_name, config_name, instances in self._policy.get_dependents(map_name, config_name)]
