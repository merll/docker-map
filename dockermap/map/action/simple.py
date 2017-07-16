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
    def get_state_actions(self, states, **kwargs):
        """
        Creates all missing containers, networks, and volumes.

        :param states: Container configuration states.
        :type states: collections.Iterable[dockermap.map.state.ConfigState]
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        return [
            ItemAction(state, ACTION_CREATE, extra_data=kwargs)
            for state in states
            if state.base_state == STATE_ABSENT
        ]


class StartActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Generally starts containers that are not running. Attached containers are skipped unless they are initial.
        Attached containers are also prepared with permissions. Where applicable, exec commands are run in started
        instance containers.

        :param states: Container configuration states.
        :type states: collections.Iterable[dockermap.map.state.ConfigState]
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        actions = []
        for state in states:
            config_type = state.config_id.config_type
            if (config_type == ITEM_TYPE_VOLUME and state.base_state == STATE_PRESENT and
                    state.state_flags & STATE_FLAG_INITIAL):
                actions.append(ItemAction(state, ACTION_START))
                actions.append(ItemAction(state, UTIL_ACTION_PREPARE_VOLUME))
            elif config_type == ITEM_TYPE_CONTAINER and state.base_state == STATE_PRESENT:
                actions.append(ItemAction(state, ACTION_START, extra_data=kwargs))
                actions.append(ItemAction(state, UTIL_ACTION_EXEC_ALL))
        return actions


class RestartActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Restarts instance containers.

        :param states: Container configuration states.
        :type states: collections.Iterable[dockermap.map.state.ConfigState]
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        return [
            ItemAction(state, ACTION_RESTART, extra_data=kwargs)
            for state in states
            if (state.config_id.config_type == ITEM_TYPE_CONTAINER and state.base_state != STATE_ABSENT and
                not state.state_flags & STATE_FLAG_INITIAL)
        ]


class StopActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Stops containers that are running. Does not check attached containers. Considers using the pre-configured
        ``stop_signal``.

        :param states: Container configuration states.
        :type states: collections.Iterable[dockermap.map.state.ConfigState]
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        return [
            ItemAction(state, UTIL_ACTION_SIGNAL_STOP, extra_data=kwargs)
            for state in states
            if (state.config_id.config_type == ITEM_TYPE_CONTAINER and state.base_state != STATE_ABSENT and
                not state.state_flags & STATE_FLAG_INITIAL)

        ]


class RemoveActionGenerator(AbstractActionGenerator):
    remove_persistent = True
    remove_attached = False
    policy_options = ['remove_persistent', 'remove_attached']

    def get_state_actions(self, states, **kwargs):
        """
        Removes containers that are stopped. Optionally skips persistent containers. Attached containers are skipped
        by default from removal but can optionally be included.

        :param states: Container configuration states.
        :type states: collections.Iterable[dockermap.map.state.ConfigState]
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        return [
            ItemAction(state, ACTION_REMOVE,
                       extra_data=kwargs if state.config_id.config_type == ITEM_TYPE_CONTAINER else None)
            for state in states
            if (state.base_state == STATE_PRESENT and (
                state.config_id.config_type == ITEM_TYPE_NETWORK or
                (state.config_id.config_type == ITEM_TYPE_VOLUME and self.remove_attached) or
                (state.config_id.config_type == ITEM_TYPE_CONTAINER and
                 self.remove_persistent or not state.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT)
            ))
        ]


class StartupActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        A combination of CreateActionGenerator and StartActionGenerator - creates and starts containers where
        appropriate.

        :param states: Container configuration states.
        :type states: collections.Iterable[dockermap.map.state.ConfigState]
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        actions = []
        for state in states:
            config_type = state.config_id.config_type
            if config_type == ITEM_TYPE_NETWORK:
                actions.append(ItemAction(state, ACTION_CREATE))
            elif config_type == ITEM_TYPE_VOLUME:
                if state.base_state == STATE_ABSENT:
                    actions.append(ItemAction(state, DERIVED_ACTION_STARTUP))
                    actions.append(ItemAction(state, UTIL_ACTION_PREPARE_VOLUME))
                elif state.base_state == STATE_PRESENT and state.state_flags & STATE_FLAG_INITIAL:
                    actions.append(ItemAction(state, ACTION_START))
                    actions.append(ItemAction(state, UTIL_ACTION_PREPARE_VOLUME))
            elif config_type == ITEM_TYPE_CONTAINER:
                if state.base_state == STATE_ABSENT:
                    actions.append(ItemAction(state, DERIVED_ACTION_STARTUP))
                    actions.append(ItemAction(state, UTIL_ACTION_EXEC_ALL))
                elif state.base_state == STATE_PRESENT:
                    actions.append(ItemAction(state, ACTION_START))
                    actions.append(ItemAction(state, UTIL_ACTION_EXEC_ALL))
        return actions


class ShutdownActionGenerator(RemoveActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        A combination of StopActionGenerator and RemoveActionGenerator - stops and removes containers where
        appropriate.

        :param states: Container configuration states.
        :type states: collections.Iterable[dockermap.map.state.ConfigState]
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        actions = []
        for state in states:
            config_type = state.config_id.config_type
            if config_type == ITEM_TYPE_NETWORK or (config_type == ITEM_TYPE_VOLUME and self.remove_attached):
                actions.append(ItemAction(state, ACTION_REMOVE))
            elif config_type == ITEM_TYPE_CONTAINER:
                if self.remove_persistent or not state.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT:
                    if state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                        actions.append(ItemAction(state, DERIVED_ACTION_SHUTDOWN))
                    elif state.base_state == STATE_PRESENT:
                        actions.append(ItemAction(state, ACTION_REMOVE))
                elif state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                    actions.append(ItemAction(state, ACTION_REMOVE))

        return actions
