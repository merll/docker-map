# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..input import ItemType
from ..state import State, StateFlags
from . import ItemAction, Action, VolumeUtilAction, ContainerUtilAction, DerivedAction
from .base import AbstractActionGenerator


class ResumeActionGenerator(AbstractActionGenerator):
    def __init__(self, *args, **kwargs):
        super(ResumeActionGenerator, self).__init__(*args, **kwargs)
        self.recreated_volumes = set()

    def get_state_actions(self, state, **kwargs):
        """
        Attached containers are created and prepared, if they are missing. They are re-created if they have terminated
        with errors. Instance containers are created if missing, started if stopped, and re-created / started if an
        attached container has been missing.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        config_type = state.config_id.config_type
        config_tuple = (state.client_name, state.config_id.map_name, state.config_id.config_name)
        if config_type == ItemType.VOLUME:
            if state.base_state == State.ABSENT:
                action = Action.CREATE
                self.recreated_volumes.add(config_tuple)
            else:
                if state.state_flags & StateFlags.NONRECOVERABLE:
                    action = DerivedAction.RESET_VOLUME
                    self.recreated_volumes.add(config_tuple)
                elif state.state_flags & StateFlags.INITIAL:
                    action = Action.START
                else:
                    return None
            return [
                ItemAction(state, action),
                ItemAction(state, VolumeUtilAction.PREPARE),
            ]
        elif config_type == ItemType.CONTAINER:
            if config_tuple in self.recreated_volumes:
                if state.base_state == State.ABSENT:
                    action = DerivedAction.STARTUP_CONTAINER
                elif state.base_state == State.RUNNING:
                    action = DerivedAction.RESET_CONTAINER
                elif state.base_state == State.PRESENT:
                    if state.base_state & StateFlags.INITIAL:
                        action = Action.START
                    else:
                        action = DerivedAction.RELAUNCH_CONTAINER
                else:
                    return None
            else:
                if state.base_state == State.ABSENT:
                    action = DerivedAction.STARTUP_CONTAINER
                else:
                    if state.state_flags & StateFlags.NONRECOVERABLE:
                        action = DerivedAction.RESET_CONTAINER
                    elif (state.base_state != State.RUNNING and
                          (state.state_flags & StateFlags.INITIAL or
                           not state.state_flags & StateFlags.PERSISTENT)):
                        action = Action.START
                    else:
                        return None
            return [
                ItemAction(state, action),
                ItemAction(state, ContainerUtilAction.EXEC_ALL),
            ]
        elif config_type == ItemType.NETWORK and state.base_state == State.ABSENT:
            return [ItemAction(state, Action.CREATE)]
