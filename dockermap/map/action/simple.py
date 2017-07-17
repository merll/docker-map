# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_VOLUME, ITEM_TYPE_NETWORK
from ..policy import CONTAINER_CONFIG_FLAG_PERSISTENT
from ..state import STATE_ABSENT, STATE_PRESENT, STATE_FLAG_INITIAL, STATE_RUNNING, STATE_FLAG_RESTARTING
from .base import AbstractActionGenerator
from . import (ItemAction, ACTION_CREATE, ACTION_START, UTIL_ACTION_PREPARE_VOLUME, ACTION_RESTART,
               UTIL_ACTION_SIGNAL_STOP, ACTION_REMOVE, UTIL_ACTION_EXEC_ALL, DERIVED_ACTION_STARTUP,
               DERIVED_ACTION_SHUTDOWN)


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
            return [ItemAction(state, ACTION_CREATE, extra_data=kwargs)]


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
                state.state_flags & STATE_FLAG_INITIAL):
            return [
                ItemAction(state, ACTION_START),
                ItemAction(state, UTIL_ACTION_PREPARE_VOLUME),
            ]
        elif config_type == ITEM_TYPE_CONTAINER and state.base_state == STATE_PRESENT:
            return [
                ItemAction(state, ACTION_START, extra_data=kwargs),
                ItemAction(state, UTIL_ACTION_EXEC_ALL),
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
                not state.state_flags & STATE_FLAG_INITIAL):
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
                not state.state_flags & STATE_FLAG_INITIAL):
            return [ItemAction(state, UTIL_ACTION_SIGNAL_STOP, extra_data=kwargs)]


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
        if state.config_id.config_type == ITEM_TYPE_CONTAINER:
            extra_data = kwargs
        else:
            extra_data = None
        if (state.base_state == STATE_PRESENT and (state.config_id.config_type == ITEM_TYPE_NETWORK or
                   (state.config_id.config_type == ITEM_TYPE_VOLUME and self.remove_attached) or
                   (state.config_id.config_type == ITEM_TYPE_CONTAINER and
                    self.remove_persistent or not state.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT))):
            return [ItemAction(state, ACTION_REMOVE, extra_data=extra_data)]


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
                    ItemAction(state, DERIVED_ACTION_STARTUP),
                    ItemAction(state, UTIL_ACTION_PREPARE_VOLUME),
                ]
            elif state.base_state == STATE_PRESENT and state.state_flags & STATE_FLAG_INITIAL:
                return [
                    ItemAction(state, ACTION_START),
                    ItemAction(state, UTIL_ACTION_PREPARE_VOLUME),
                ]
        elif config_type == ITEM_TYPE_CONTAINER:
            if state.base_state == STATE_ABSENT:
                return [
                    ItemAction(state, DERIVED_ACTION_STARTUP),
                    ItemAction(state, UTIL_ACTION_EXEC_ALL),
                ]
            elif state.base_state == STATE_PRESENT:
                return [
                    ItemAction(state, ACTION_START),
                    ItemAction(state, UTIL_ACTION_EXEC_ALL),
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
        if config_type == ITEM_TYPE_NETWORK or (config_type == ITEM_TYPE_VOLUME and self.remove_attached):
            return [ItemAction(state, ACTION_REMOVE)]
        elif config_type == ITEM_TYPE_CONTAINER:
            if self.remove_persistent or not state.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT:
                if state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                    return [ItemAction(state, DERIVED_ACTION_SHUTDOWN)]
                elif state.base_state == STATE_PRESENT:
                    return [ItemAction(state, ACTION_REMOVE)]
            elif state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                return [ItemAction(state, ACTION_REMOVE)]
