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
    @abstractmethod
    def get_state_actions(self, states):
        """

        :param states: Container configuration states tuple.
        :type states: dockermap.map.state.ContainerConfigStates
        :return: Expanded list of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        pass
