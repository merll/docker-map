# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from . import State, StateFlags
from .base import DependencyStateGenerator, ContainerBaseState, NetworkBaseState


class InitialContainerState(ContainerBaseState):
    """
    Assumes every container to be absent. This is intended for testing and situations where the actual state
    cannot be determined.
    """
    def inspect(self):
        # No need to actually make any client call
        pass

    def get_state(self):
        return State.ABSENT, StateFlags.NONE, {}


class InitialNetworkState(NetworkBaseState):
    """
    Assumes every network to be absent. This is intended for testing and situations where the actual state
    cannot be determined.
    """
    def inspect(self):
        # No need to actually make any client call
        pass

    def get_state(self):
        return State.ABSENT, StateFlags.NONE, {}


class InitialStateGenerator(DependencyStateGenerator):
    container_state_class = InitialContainerState
    network_state_class = InitialNetworkState
