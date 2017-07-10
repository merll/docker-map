# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_VOLUME, ITEM_TYPE_NETWORK
from ..policy import CONTAINER_CONFIG_FLAG_PERSISTENT
from ..state import STATE_ABSENT, STATE_PRESENT, STATE_FLAG_INITIAL, STATE_RUNNING, STATE_FLAG_RESTARTING
from .base import AbstractActionGenerator
from . import (ClientMapActions, ItemAction, ACTION_CREATE, ACTION_START, UTIL_ACTION_PREPARE_VOLUME, ACTION_RESTART,
               UTIL_ACTION_SIGNAL_STOP, ACTION_REMOVE, UTIL_ACTION_EXEC_ALL, DERIVED_ACTION_STARTUP,
               DERIVED_ACTION_SHUTDOWN)


class CreateActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Creates all missing containers.

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
        actions.extend([
            ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, ACTION_CREATE)
            for state in states.volumes
            if state.base_state == STATE_ABSENT
        ])
        actions.extend([
            ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, ACTION_CREATE, extra_data=kwargs)
            for state in states.containers
            if state.base_state == STATE_ABSENT
        ])
        return ClientMapActions(states.client, states.map, actions)


class StartActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Generally starts containers that are not running. Attached containers are skipped unless they are initial.
        Attached containers are also prepared with permissions. Where applicable, exec commands are run in started
        instance containers.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: dockermap.map.action.ClientMapActions
        """
        actions = []
        for state in states.volumes:
            if state.base_state == STATE_PRESENT and state.state_flags & STATE_FLAG_INITIAL:
                actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, ACTION_START))
                actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, UTIL_ACTION_PREPARE_VOLUME))

        for state in states.containers:
            if state.base_state == STATE_PRESENT:
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, ACTION_START,
                                          extra_data=kwargs))
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, UTIL_ACTION_EXEC_ALL))

        return ClientMapActions(states.client, states.map, actions)


class RestartActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Restarts instance containers.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: dockermap.map.action.ClientMapActions
        """
        actions = [
            ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, ACTION_RESTART, extra_data=kwargs)
            for state in states.containers
            if state.base_state != STATE_ABSENT and not state.state_flags & STATE_FLAG_INITIAL
        ]
        return ClientMapActions(states.client, states.map, actions)


class StopActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Stops containers that are running. Does not check attached containers. Considers using the pre-configured
        ``stop_signal``.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: dockermap.map.action.ClientMapActions
        """
        actions = [
            ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, UTIL_ACTION_SIGNAL_STOP, extra_data=kwargs)
            for state in states.containers
            if state.base_state != STATE_ABSENT and not state.state_flags & STATE_FLAG_INITIAL
        ]
        return ClientMapActions(states.client, states.map, actions)


class RemoveActionGenerator(AbstractActionGenerator):
    remove_persistent = True
    remove_attached = False
    policy_options = ['remove_persistent', 'remove_attached']

    def get_state_actions(self, states, **kwargs):
        """
        Removes containers that are stopped. Optionally skips persistent containers. Attached containers are skipped
        by default from removal but can optionally be included.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: dockermap.map.action.ClientMapActions
        """
        if self.remove_persistent:
            actions = [
                ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, ACTION_REMOVE, extra_data=kwargs)
                for state in states.containers
                if state.base_state == STATE_PRESENT
            ]
        else:
            actions = [
                ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, ACTION_REMOVE,
                           extra_data=kwargs)
                for state in states.containers
                if state.base_state == STATE_PRESENT and not states.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT
            ]

        if self.remove_attached:
            actions.extend([
                ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, ACTION_REMOVE)
                for state in states.volumes
                if state.base_state == STATE_PRESENT
            ])

        actions.extend([
            ItemAction(ITEM_TYPE_NETWORK, state.config, action_types=ACTION_REMOVE, extra_data=kwargs)
            for state in states.networks
            if state.base_state == STATE_PRESENT
        ])

        return ClientMapActions(states.client, states.map, actions)


class StartupActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        A combination of CreateActionGenerator and StartActionGenerator - creates and starts containers where
        appropriate.

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

        for state in states.volumes:
            if state.base_state == STATE_ABSENT:
                actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance,
                                          DERIVED_ACTION_STARTUP))
                actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance,
                                          UTIL_ACTION_PREPARE_VOLUME))
            elif state.base_state == STATE_PRESENT and state.state_flags & STATE_FLAG_INITIAL:
                actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, ACTION_START))
                actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance,
                                          UTIL_ACTION_PREPARE_VOLUME))

        for state in states.containers:
            if state.base_state == STATE_ABSENT:
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance,
                                          DERIVED_ACTION_STARTUP))
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance,
                                          UTIL_ACTION_EXEC_ALL))
            elif state.base_state == STATE_PRESENT:
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance,
                                          ACTION_START))
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance,
                                          UTIL_ACTION_EXEC_ALL))

        return ClientMapActions(states.client, states.map, actions)


class ShutdownActionGenerator(RemoveActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        A combination of StopActionGenerator and RemoveActionGenerator - stops and removes containers where
        appropriate.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: dockermap.map.action.ClientMapActions
        """
        actions = []
        for state in states.containers:
            if self.remove_persistent or not state.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT:
                if state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                    actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance,
                                              DERIVED_ACTION_SHUTDOWN))
                elif state.base_state == STATE_PRESENT:
                    actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, ACTION_REMOVE))
            elif state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, ACTION_REMOVE))

        if self.remove_attached:
            actions.extend([
                ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, ACTION_REMOVE)
                for state in states.volumes
                if state.base_state == STATE_PRESENT
            ])

        actions.extend([
            ItemAction(ITEM_TYPE_NETWORK, state.config, action_types=ACTION_REMOVE, extra_data=kwargs)
            for state in states.networks
            if state.base_state == STATE_PRESENT
        ])

        return ClientMapActions(states.client, states.map, actions)
