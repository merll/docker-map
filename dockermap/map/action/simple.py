# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..action import DERIVED_ACTION_STARTUP, DERIVED_ACTION_SHUTDOWN
from ..policy import CONFIG_FLAG_PERSISTENT
from ..state import STATE_ABSENT, STATE_PRESENT, STATE_FLAG_INITIAL, STATE_RUNNING, STATE_FLAG_RESTARTING
from .base import AbstractActionGenerator
from . import (InstanceAction, ACTION_CREATE, ACTION_START, UTIL_ACTION_PREPARE_CONTAINER,
               ACTION_RESTART, UTIL_ACTION_SIGNAL_STOP, ACTION_REMOVE, UTIL_ACTION_EXEC_ALL)


class CreateActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Creates all missing containers.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)
        attached_actions = [
            new_action(attached_state.instance, ACTION_CREATE)
            for attached_state in states.attached
            if attached_state.base_state == STATE_ABSENT
        ]
        instance_actions = [
            new_action(instance_state.instance, ACTION_CREATE, extra_data=kwargs)
            for instance_state in states.instances
            if instance_state.base_state == STATE_ABSENT
        ]
        return attached_actions, instance_actions


class StartActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Generally starts containers that are not running. Attached containers are skipped unless they are initial.
        Attached containers are also prepared with permissions. Where applicable, exec commands are run in started
        instance containers.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)
        attached_actions = []
        for attached_state in states.attached:
            if attached_state.base_state == STATE_PRESENT and attached_state.flags & STATE_FLAG_INITIAL:
                attached_actions.append(new_action(attached_state.instance, ACTION_START))
                attached_actions.append(new_action(attached_state.instance, UTIL_ACTION_PREPARE_CONTAINER))

        instance_actions = []
        for instance_state in states.instances:
            if instance_state.base_state == STATE_PRESENT:
                instance_actions.append(new_action(instance_state.instance, ACTION_START, extra_data=kwargs))
                instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_ALL))

        return attached_actions, instance_actions


class RestartActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Restarts instance containers.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)
        instance_actions = [
            new_action(instance_state.instance, ACTION_RESTART, extra_data=kwargs)
            for instance_state in states.instances
            if instance_state.base_state != STATE_ABSENT and not instance_state.flags & STATE_FLAG_INITIAL
        ]
        return [], instance_actions


class StopActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Stops containers that are running. Does not check attached containers. Considers using the pre-configured
        ``stop_signal``.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)
        instance_actions = [
            new_action(instance_state.instance, UTIL_ACTION_SIGNAL_STOP, extra_data=kwargs)
            for instance_state in states.instances
            if instance_state.base_state != STATE_ABSENT and not instance_state.flags & STATE_FLAG_INITIAL
        ]
        return [], instance_actions


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
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)
        if self.remove_attached:
            attached_actions = [
                new_action(attached_state.instance, ACTION_REMOVE)
                for attached_state in states.attached
                if attached_state.base_state == STATE_PRESENT
            ]
        else:
            attached_actions = []

        if self.remove_persistent:
            instance_actions = [
                new_action(instance_state.instance, ACTION_REMOVE, extra_data=kwargs)
                for instance_state in states.instances
                if instance_state.base_state == STATE_PRESENT
            ]
        else:
            instance_actions = [
                new_action(instance_state.instance, ACTION_REMOVE, extra_data=kwargs)
                for instance_state in states.instances
                if instance_state.base_state == STATE_PRESENT and not states.flags & CONFIG_FLAG_PERSISTENT
            ]

        return attached_actions, instance_actions


class StartupActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        A combination of CreateActionGenerator and StartActionGenerator - creates and starts containers where
        appropriate.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)

        attached_actions = []
        for attached_state in states.attached:
            if attached_state.base_state == STATE_ABSENT:
                attached_actions.append(new_action(attached_state.instance, DERIVED_ACTION_STARTUP))
                attached_actions.append(new_action(attached_state.instance, UTIL_ACTION_PREPARE_CONTAINER))
            elif attached_state.base_state == STATE_PRESENT and attached_state.flags & STATE_FLAG_INITIAL:
                attached_actions.append(new_action(attached_state.instance, ACTION_START))
                attached_actions.append(new_action(attached_state.instance, UTIL_ACTION_PREPARE_CONTAINER))

        instance_actions = []
        for instance_state in states.instances:
            if instance_state.base_state == STATE_ABSENT:
                instance_actions.append(new_action(instance_state.instance, DERIVED_ACTION_STARTUP))
                instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_ALL))
            elif instance_state.base_state == STATE_PRESENT:
                instance_actions.append(new_action(instance_state.instance, ACTION_START))
                instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_ALL))

        return attached_actions, instance_actions


class ShutdownActionGenerator(RemoveActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        A combination of StopActionGenerator and RemoveActionGenerator - stops and removes containers where
        appropriate.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)

        if self.remove_attached:
            attached_actions = [
                new_action(attached_state.instance, ACTION_REMOVE)
                for attached_state in states.attached
                if attached_state.base_state == STATE_PRESENT
            ]
        else:
            attached_actions = []

        instance_actions = []
        if self.remove_persistent or not states.flags & CONFIG_FLAG_PERSISTENT:
            for instance_state in states.instances:
                if instance_state.base_state == STATE_RUNNING or instance_state.flags & STATE_FLAG_RESTARTING:
                    instance_actions.append(new_action(instance_state.instance, DERIVED_ACTION_SHUTDOWN))
                elif instance_state.base_state == STATE_PRESENT:
                    instance_actions.append(new_action(instance_state.instance, ACTION_REMOVE))

        return attached_actions, instance_actions
