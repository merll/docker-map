# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import abstractmethod

from six import with_metaclass

from ..policy import ABCPolicyUtilMeta, PolicyUtil


class AbstractActionGenerator(with_metaclass(ABCPolicyUtilMeta, PolicyUtil)):
    """
    Abstract base class for action generators, which determine what actions are to be executed based on current
    container states.
    """
    @abstractmethod
    def get_state_actions(self, states, **kwargs):
        """
        Generates actions from a container configuration state. The output is a tuple of two lists: Actions to
        attached containers and actions to instance containers.

        :param states: Container configuration states tuple.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: Expanded list of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        pass
