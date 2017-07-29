# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_VOLUME, ITEM_TYPE_NETWORK
from ..policy import ConfigFlags
from ..state import STATE_ABSENT, STATE_PRESENT, STATE_RUNNING, StateFlags
from .base import AbstractActionGenerator
from . import (ItemAction, ACTION_CREATE, ACTION_START, ACTION_RESTART, ACTION_REMOVE, V_UTIL_ACTION_PREPARE,
               C_UTIL_ACTION_SIGNAL_STOP, C_UTIL_ACTION_EXEC_ALL, C_UTIL_ACTION_CONNECT_ALL,
               N_UTIL_ACTION_DISCONNECT_ALL, DERIVED_ACTION_STARTUP_CONTAINER, DERIVED_ACTION_SHUTDOWN_CONTAINER,
               DERIVED_ACTION_STARTUP_VOLUME)


class CreateActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, state, **kwargs):
        """
        Creates all missing containers, networks, and volumes.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        if state.base_state == STATE_ABSENT:
            actions = [ItemAction(state, ACTION_CREATE, extra_data=kwargs)]
            if state.config_id.config_type == ITEM_TYPE_CONTAINER:
                actions.append(ItemAction(state, C_UTIL_ACTION_CONNECT_ALL))
            return actions


class StartActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, state, **kwargs):
        """
        Generally starts containers that are not running. Attached containers are skipped unless they are initial.
        Attached containers are also prepared with permissions. Where applicable, exec commands are run in started
        instance containers.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        config_type = state.config_id.config_type
        if (config_type == ITEM_TYPE_VOLUME and state.base_state == STATE_PRESENT and
                state.state_flags & StateFlags.INITIAL):
            return [
                ItemAction(state, ACTION_START),
                ItemAction(state, V_UTIL_ACTION_PREPARE),
            ]
        elif config_type == ITEM_TYPE_CONTAINER and state.base_state == STATE_PRESENT:
            return [
                ItemAction(state, ACTION_START, extra_data=kwargs),
                ItemAction(state, C_UTIL_ACTION_EXEC_ALL),
            ]


class RestartActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, state, **kwargs):
        """
        Restarts instance containers.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        if (state.config_id.config_type == ITEM_TYPE_CONTAINER and state.base_state != STATE_ABSENT and
                not state.state_flags & StateFlags.INITIAL):
            return [ItemAction(state, ACTION_RESTART, extra_data=kwargs)]


class StopActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, state, **kwargs):
        """
        Stops containers that are running. Does not check attached containers. Considers using the pre-configured
        ``stop_signal``.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        if (state.config_id.config_type == ITEM_TYPE_CONTAINER and state.base_state != STATE_ABSENT and
                not state.state_flags & StateFlags.INITIAL):
            return [ItemAction(state, C_UTIL_ACTION_SIGNAL_STOP, extra_data=kwargs)]


class RemoveActionGenerator(AbstractActionGenerator):
    remove_persistent = True
    remove_attached = False
    policy_options = ['remove_persistent', 'remove_attached']

    def get_state_actions(self, state, **kwargs):
        """
        Removes containers that are stopped. Optionally skips persistent containers. Attached containers are skipped
        by default from removal but can optionally be included.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        config_type = state.config_id.config_type
        if config_type == ITEM_TYPE_CONTAINER:
            extra_data = kwargs
        else:
            extra_data = None
        if state.base_state == STATE_PRESENT:
            if ((config_type == ITEM_TYPE_VOLUME and self.remove_attached) or
                    (config_type == ITEM_TYPE_CONTAINER and
                     self.remove_persistent or not state.config_flags & ConfigFlags.CONTAINER_PERSISTENT)):
                return [ItemAction(state, ACTION_REMOVE, extra_data=extra_data)]
            elif config_type == ITEM_TYPE_NETWORK:
                connected_containers = state.extra_data.get('containers')
                if connected_containers:
                    actions = [ItemAction(state, N_UTIL_ACTION_DISCONNECT_ALL, {'containers': connected_containers})]
                else:
                    actions = []
                actions.append(ItemAction(state, ACTION_REMOVE, extra_data=kwargs))
                return actions


class StartupActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, state, **kwargs):
        """
        A combination of CreateActionGenerator and StartActionGenerator - creates and starts containers where
        appropriate.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        config_type = state.config_id.config_type
        if config_type == ITEM_TYPE_NETWORK:
            return [ItemAction(state, ACTION_CREATE)]
        elif config_type == ITEM_TYPE_VOLUME:
            if state.base_state == STATE_ABSENT:
                return [
                    ItemAction(state, DERIVED_ACTION_STARTUP_VOLUME),
                    ItemAction(state, V_UTIL_ACTION_PREPARE),
                ]
            elif state.base_state == STATE_PRESENT and state.state_flags & StateFlags.INITIAL:
                return [
                    ItemAction(state, ACTION_START),
                    ItemAction(state, V_UTIL_ACTION_PREPARE),
                ]
        elif config_type == ITEM_TYPE_CONTAINER:
            if state.base_state == STATE_ABSENT:
                return [
                    ItemAction(state, DERIVED_ACTION_STARTUP_CONTAINER),
                    ItemAction(state, C_UTIL_ACTION_EXEC_ALL),
                ]
            elif state.base_state == STATE_PRESENT:
                return [
                    ItemAction(state, ACTION_START),
                    ItemAction(state, C_UTIL_ACTION_EXEC_ALL),
                ]


class ShutdownActionGenerator(RemoveActionGenerator):
    def get_state_actions(self, state, **kwargs):
        """
        A combination of StopActionGenerator and RemoveActionGenerator - stops and removes containers where
        appropriate.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        config_type = state.config_id.config_type
        if config_type == ITEM_TYPE_NETWORK:
            if state.base_state == STATE_PRESENT:
                connected_containers = state.extra_data.get('containers')
                if connected_containers:
                    cc_names = [c.get('Name', c['Id']) for c in connected_containers]
                    actions = [ItemAction(state, N_UTIL_ACTION_DISCONNECT_ALL,
                                          extra_data={'containers': cc_names})]
                else:
                    actions = []
                actions.append(ItemAction(state, ACTION_REMOVE, extra_data=kwargs))
                return actions
        elif config_type == ITEM_TYPE_VOLUME and self.remove_attached:
            return [ItemAction(state, ACTION_REMOVE)]
        elif config_type == ITEM_TYPE_CONTAINER:
            if self.remove_persistent or not state.config_flags & ConfigFlags.CONTAINER_PERSISTENT:
                if state.base_state == STATE_RUNNING or state.state_flags & StateFlags.RESTARTING:
                    return [ItemAction(state, DERIVED_ACTION_SHUTDOWN_CONTAINER)]
                elif state.base_state == STATE_PRESENT:
                    return [ItemAction(state, ACTION_REMOVE)]
            elif state.base_state == STATE_RUNNING or state.state_flags & StateFlags.RESTARTING:
                return [ItemAction(state, ACTION_REMOVE)]
