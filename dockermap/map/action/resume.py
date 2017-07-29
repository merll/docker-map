# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_VOLUME, ITEM_TYPE_NETWORK
from ..policy import ConfigFlags
from ..state import STATE_PRESENT, STATE_ABSENT, STATE_RUNNING, StateFlags
from .base import AbstractActionGenerator
from . import (ItemAction, DERIVED_ACTION_STARTUP_CONTAINER, DERIVED_ACTION_STARTUP_VOLUME,
               DERIVED_ACTION_RELAUNCH_CONTAINER, DERIVED_ACTION_RELAUNCH_VOLUME, ACTION_START, V_UTIL_ACTION_PREPARE,
               DERIVED_ACTION_RESET_CONTAINER, C_UTIL_ACTION_EXEC_ALL, ACTION_CREATE)


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
        if config_type == ITEM_TYPE_NETWORK:
            return [ItemAction(state, ACTION_CREATE)]
        elif config_type == ITEM_TYPE_VOLUME:
            if state.base_state == STATE_ABSENT:
                action = DERIVED_ACTION_STARTUP_VOLUME
                self.recreated_volumes.add(config_tuple)
            else:
                if state.state_flags & StateFlags.NONRECOVERABLE:
                    action = DERIVED_ACTION_RELAUNCH_VOLUME
                    self.recreated_volumes.add(config_tuple)
                elif state.state_flags & StateFlags.INITIAL:
                    action = ACTION_START
                else:
                    return None
            return [
                ItemAction(state, action),
                ItemAction(state, V_UTIL_ACTION_PREPARE),
            ]
        elif config_type == ITEM_TYPE_CONTAINER:
            if config_tuple in self.recreated_volumes:
                if state.base_state == STATE_ABSENT:
                    action = DERIVED_ACTION_STARTUP_CONTAINER
                elif state.base_state == STATE_RUNNING:
                    action = DERIVED_ACTION_RESET_CONTAINER
                elif state.base_state == STATE_PRESENT:
                    if state.base_state & StateFlags.INITIAL:
                        action = ACTION_START
                    else:
                        action = DERIVED_ACTION_RELAUNCH_CONTAINER
                else:
                    return None
            else:
                if state.base_state == STATE_ABSENT:
                    action = DERIVED_ACTION_STARTUP_CONTAINER
                else:
                    if state.state_flags & StateFlags.NONRECOVERABLE:
                        action = DERIVED_ACTION_RESET_CONTAINER
                    elif (state.base_state != STATE_RUNNING and
                          (state.state_flags & StateFlags.INITIAL or
                           not state.config_flags & ConfigFlags.CONTAINER_PERSISTENT)):
                        action = ACTION_START
                    else:
                        return None
            return [
                ItemAction(state, action),
                ItemAction(state, C_UTIL_ACTION_EXEC_ALL),
            ]
