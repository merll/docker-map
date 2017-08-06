# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from . import State, StateFlags
from .base import DependencyStateGenerator, AbstractState


class InitialState(AbstractState):
    """
    Assumes every item to be absent. This is intended for testing and situations where the actual state
    cannot be determined.
    """
    def inspect(self):
        # No need to actually make any client call
        pass

    def get_state(self):
        return State.ABSENT, StateFlags.NONE, {}


class InitialStateGenerator(DependencyStateGenerator):
    container_state_class = InitialState
    network_state_class = InitialState
    image_state_class = InitialState
