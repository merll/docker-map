# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod

from six import with_metaclass

from ..policy import PolicyUtil


class AbstractActionGenerator(with_metaclass(ABCMeta, PolicyUtil)):
    """
    Abstract base class for action generators, which determine what actions are to be executed based on current
    container states.
    """
    def expand_attached_actions(self, actions):
        """

        :param actions: Action list to expand.
        :type actions: list[dockermap.map.action.InstanceAction]
        :rtype: __generator[dockermap.map.action.InstanceAction]
        """
        for action in actions:
            if isinstance(action.action_type, (list, tuple)):
                for sub_type in action.action_type:
                    yield action.copy(action_type=sub_type, extra_data=action.extra_data)
            else:
                yield action

    def expand_instance_actions(self, actions):
        """

        :param actions: Action list to expand.
        :type actions: list[dockermap.map.action.InstanceAction]
        :rtype: __generator[dockermap.map.action.InstanceAction]
        """
        for action in actions:
            if isinstance(action.action_type, (list, tuple)):
                for sub_type in action.action_type:
                    yield action.copy(action_type=sub_type, extra_data=action.extra_data)
            else:
                yield action

    @abstractmethod
    def get_state_actions(self, states):
        """

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        pass

    def get_actions(self, states):
        """

        :param states: Container configuration states tuple.
        :type states: dockermap.map.state.ContainerConfigStates
        :return: Expanded list of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        attached_actions, instance_actions = self.get_state_actions(states)
        expanded_attached = list(self.expand_attached_actions(attached_actions))
        expanded_instance = list(self.expand_instance_actions(instance_actions))
        return expanded_attached, expanded_instance
