# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
from abc import abstractmethod
import logging

from six import with_metaclass

from ..policy import (CONFIG_FLAG_DEPENDENT, CONFIG_FLAG_ATTACHED, CONFIG_FLAG_PERSISTENT,
                      ABCPolicyUtilMeta, PolicyUtil, ForwardGeneratorMixin, ReverseGeneratorMixin)
from . import (INITIAL_START_TIME, STATE_ABSENT, STATE_PRESENT, STATE_RUNNING, STATE_FLAG_INITIAL,
               STATE_FLAG_RESTARTING, STATE_FLAG_NONRECOVERABLE, ContainerConfigStates, ContainerInstanceState)


log = logging.getLogger(__name__)


class AbstractStateGenerator(with_metaclass(ABCPolicyUtilMeta, PolicyUtil)):
    """
    Abstract base implementation for an state generator, which determines the current state of containers on the client.
    """
    nonrecoverable_exit_codes = (-127, -1)
    policy_options = ['nonrecoverable_exit_codes']

    def get_container_state(self, map_name, container_map, config_name, container_config, client_name, client_config,
                            client, instance_alias, config_flags=0):
        """
        Fetches information about the container from the client and determines a base state. To be extended by
        subclasses as necessary.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param client: Docker client.
        :type client: docker.client.Client
        :param instance_alias: Container instance name or attached alias.
        :type instance_alias: unicode | str
        :param config_flags: Config flags on the container.
        :type config_flags: int
        :return: Tuple of container inspection detail, and the base state information derived from that.
        :rtype: (dict | NoneType, unicode | str, int, dict)
        """
        if config_flags & CONFIG_FLAG_ATTACHED:
            if container_map.use_attached_parent_name:
                container_name = self._policy.aname(map_name, instance_alias, config_name)
            else:
                container_name = self._policy.aname(map_name, instance_alias)
        else:
            container_name = self._policy.cname(map_name, config_name, instance_alias)

        if container_name in self._policy.container_names[client_name]:
            c_detail = client.inspect_container(container_name)
            c_status = c_detail['State']
            if c_status['Running']:
                return c_detail, STATE_RUNNING, 0, {}
            if c_status['StartedAt'] == INITIAL_START_TIME:
                state_flag = STATE_FLAG_INITIAL
            elif c_status['ExitCode'] in self.nonrecoverable_exit_codes:
                state_flag = STATE_FLAG_NONRECOVERABLE
            else:
                state_flag = 0
            if c_status['Restarting']:
                state_flag |= STATE_FLAG_RESTARTING
            return c_detail, STATE_PRESENT, state_flag, {}
        return None, STATE_ABSENT, 0, {}

    def generate_config_states(self, map_name, c_map, config_name, c_config, instances, client_names=None,
                               is_dependency=False):
        """
        Generates the actions on a single item, which can be either a dependency or a explicitly selected
        container.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param c_map: Container map instance.
        :type c_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param c_config: Container configuration object.
        :type c_config: dockermap.map.config.ContainerConfiguration
        :param instances: Instance names as a list. Can be ``[None]``
        :type instances: list[unicode | str]
        :param client_names: Optional client list. By default uses the client list from the map or configuration.
        :type client_names: list[unicode | str]
        :param is_dependency: Whether the state check is on a dependency or dependent container.
        :type is_dependency: bool
        :return: Generator for container state information.
        :rtype: __generator[dockermap.map.state.ContainerConfigStates]
        """
        config_flags = CONFIG_FLAG_DEPENDENT if is_dependency else 0
        a_flags = config_flags | CONFIG_FLAG_ATTACHED
        if c_config.persistent:
            config_flags |= CONFIG_FLAG_PERSISTENT
        if client_names is not None:
            clients = [cc for cc in self._policy.get_clients(c_config, c_map) if cc[0] in client_names]
        else:
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
            instance_states = [i_state for i_state in _get_state(config_flags, instances)]
            states = ContainerConfigStates(client_name, map_name, config_name, config_flags, instance_states,
                                           attached_states)
            log.debug("Container state information: %s", states)
            yield states

    @abstractmethod
    def get_states(self, map_name, config_name, instances=None):
        """
        To be implemented by subclasses. Generates state information for the selected container(s).

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param config_name: Main container configuration name.
        :type config_name: unicode | str
        :param instances: Instance names.
        :type instances: list or tuple
        :return: Return values of created main containers.
        :rtype: __generator[dockermap.map.state.ContainerConfigStates]
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
    def get_states(self, map_name, config_name, instances=None, client_names=None):
        """
        Generates state information for the selected container.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param config_name: Main container configuration name.
        :type config_name: unicode | str
        :param instances: Optional instance names. By default follows the instances from the configuration.
        :type instances: list[unicode | str]
        :param client_names: Optional client list. By default uses the client list from the map or configuration.
        :type client_names: list[unicode | str]
        :return: Return values of created main containers.
        :rtype: __generator[dockermap.map.state.ContainerConfigStates]
        """
        c_map = self._policy.container_maps[map_name]
        c_config = c_map.get_existing(config_name)
        if not c_config:
            raise KeyError("Container configuration '{0}' not found on map '{1}'.".format(
                config_name, map_name))
        if not instances:
            c_instances = c_config.instances or [None]
        elif isinstance(instances, (tuple, list)):
            c_instances = instances
        else:
            c_instances = [instances]
        return self.generate_config_states(map_name, c_map, config_name, c_config, c_instances,
                                           client_names=client_names)


class AbstractDependencyStateGenerator(with_metaclass(ABCPolicyUtilMeta, SingleStateGenerator)):
    @abstractmethod
    def get_dependency_path(self, map_name, config_name, client_names=None):
        """
        To be implemented by subclasses (or using :class:`ForwardActionGeneratorMixin` or
        :class:`ReverseActionGeneratorMixin`). Should provide an iterable of objects to be handled before the explicitly
        selected container configuration.

        :param map_name: Container map name.
        :param config_name: Container configuration name.
        :param client_names: Optional client list. By default uses the client list from the map or each configuration.
        :type client_names: list[unicode | str]
        :return: Iterable of dependency objects in tuples of map name, container (config) name, instance.
        :rtype: list[tuple]
        """
        pass

    def get_dependency_states(self, map_name, config_name, client_names=None):
        """
        Generates state information for a container configuration dependencies / dependents.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param config_name: Main container configuration name.
        :type config_name: unicode | str
        :param client_names: Optional client list. By default uses the client list from the map or each configuration.
        :type client_names: list[unicode | str]
        :return: Return values of created main containers.
        :rtype: __generator[dockermap.map.state.ContainerConfigStates]
        """
        dependency_path = self.get_dependency_path(map_name, config_name)
        log.debug("Following dependency path for %s.%s.", map_name, config_name)
        for d_map_name, d_map, d_config_name, d_config, d_instances in dependency_path:
            log.debug("Dependency path at %s.%s, instances %s.", d_map_name, d_config_name, d_instances)
            for state in self.generate_config_states(d_map_name, d_map, d_config_name, d_config, d_instances,
                                                     client_names=client_names, is_dependency=True):
                yield state

    def get_states(self, map_name, config_name, instances=None, client_names=None):
        """
        Generates state information for the selected container and its dependencies / dependents.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param config_name: Main container configuration name.
        :type config_name: unicode | str
        :param instances: Instance names.
        :type instances: list or tuple
        :param client_names: Optional client list. By default uses the client list from the map or configuration.
        :type client_names: list[unicode | str]
        :return: Return values of created main containers.
        :rtype: itertools.chain[dockermap.map.state.ContainerConfigStates]
        """
        return itertools.chain(
            self.get_dependency_states(map_name, config_name, client_names=client_names),
            super(AbstractDependencyStateGenerator, self).get_states(map_name, config_name, instances=instances,
                                                                     client_names=client_names)
        )


class DependencyStateGenerator(ForwardGeneratorMixin, AbstractDependencyStateGenerator):
    pass


class DependentStateGenerator(ReverseGeneratorMixin, AbstractDependencyStateGenerator):
    pass
