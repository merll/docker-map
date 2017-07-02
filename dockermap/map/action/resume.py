# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..policy import CONTAINER_CONFIG_FLAG_PERSISTENT
from ..state import STATE_PRESENT, STATE_FLAG_NONRECOVERABLE, STATE_FLAG_INITIAL, STATE_ABSENT, STATE_RUNNING
from .base import AbstractActionGenerator
from . import (ItemAction, ClientMapActions, ITEM_TYPE_VOLUME, ITEM_TYPE_CONTAINER, ITEM_TYPE_NETWORK,
               DERIVED_ACTION_STARTUP, DERIVED_ACTION_RELAUNCH, ACTION_START, UTIL_ACTION_PREPARE_VOLUME,
               DERIVED_ACTION_RESET, UTIL_ACTION_EXEC_ALL, ACTION_CREATE)


class ResumeActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Attached containers are created and prepared, if they are missing. They are re-created if they have terminated
        with errors. Instance containers are created if missing, started if stopped, and re-created / started if an
        attached container has been missing.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: dockermap.map.action.ClientMapActions
        """
        actions = [
            ItemAction(ITEM_TYPE_NETWORK, state.config, action_type=ACTION_CREATE, extra_data=kwargs)
            for state in states.networks
            if state.base_state == STATE_ABSENT
        ]
        recreate_attached = False
        for state in states.volumes:
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
                    continue
            actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, action))
            actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, UTIL_ACTION_PREPARE_VOLUME))

        if recreate_attached:
            for state in states.containers:
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
                    continue
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, action))
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, UTIL_ACTION_EXEC_ALL))
        else:
            for state in states.containers:
                if state.base_state == STATE_ABSENT:
                    action = DERIVED_ACTION_STARTUP
                else:
                    if state.state_flags & STATE_FLAG_NONRECOVERABLE:
                        action = DERIVED_ACTION_RESET
                    elif (state.base_state != STATE_RUNNING and
                          (state.state_flags & STATE_FLAG_INITIAL or
                           not states.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT)):
                        action = ACTION_START
                    else:
                        continue
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, action))
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, UTIL_ACTION_EXEC_ALL))

        return ClientMapActions(states.client, states.map, actions)
