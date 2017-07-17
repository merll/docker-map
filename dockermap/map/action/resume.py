# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_VOLUME, ITEM_TYPE_NETWORK
from ..policy import CONTAINER_CONFIG_FLAG_PERSISTENT
from ..state import STATE_PRESENT, STATE_FLAG_NONRECOVERABLE, STATE_FLAG_INITIAL, STATE_ABSENT, STATE_RUNNING
from .base import AbstractActionGenerator
from . import (ItemAction, DERIVED_ACTION_STARTUP, DERIVED_ACTION_RELAUNCH, ACTION_START, UTIL_ACTION_PREPARE_VOLUME,
               DERIVED_ACTION_RESET, UTIL_ACTION_EXEC_ALL, ACTION_CREATE)


class ResumeActionGenerator(AbstractActionGenerator):
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
        actions = []
        recreate_attached = False  # FIXME: This is no longer evaluated with the new iteration method.
        config_type = state.config_id.config_type
        if config_type == ITEM_TYPE_NETWORK:
            actions.append(ItemAction(state, ACTION_CREATE))
        elif config_type == ITEM_TYPE_VOLUME:
            if state.base_state == STATE_ABSENT:
                action = DERIVED_ACTION_STARTUP
                recreate_attached = True
            else:
                if state.state_flags & STATE_FLAG_NONRECOVERABLE:
                    action = DERIVED_ACTION_RELAUNCH
                    recreate_attached = True
                elif state.state_flags & STATE_FLAG_INITIAL:
                    action = ACTION_START
                else:
                    return actions
            actions.append(ItemAction(state, action))
            actions.append(ItemAction(state, UTIL_ACTION_PREPARE_VOLUME))
        elif config_type == ITEM_TYPE_CONTAINER:
            if recreate_attached:
                if state.base_state == STATE_ABSENT:
                    action = DERIVED_ACTION_STARTUP
                elif state.base_state == STATE_RUNNING:
                    action = DERIVED_ACTION_RESET
                elif state.base_state == STATE_PRESENT:
                    if state.base_state & STATE_FLAG_INITIAL:
                        action = ACTION_START
                    else:
                        action = DERIVED_ACTION_RELAUNCH
                else:
                    return actions
                actions.append(ItemAction(state, action))
                actions.append(ItemAction(state, UTIL_ACTION_EXEC_ALL))
            else:
                if state.base_state == STATE_ABSENT:
                    action = DERIVED_ACTION_STARTUP
                else:
                    if state.state_flags & STATE_FLAG_NONRECOVERABLE:
                        action = DERIVED_ACTION_RESET
                    elif (state.base_state != STATE_RUNNING and
                          (state.state_flags & STATE_FLAG_INITIAL or
                           not state.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT)):
                        action = ACTION_START
                    else:
                        return actions
                actions.append(ItemAction(state, action))
                actions.append(ItemAction(state, UTIL_ACTION_EXEC_ALL))

        return actions
