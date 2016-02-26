# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..policy import CONFIG_FLAG_PERSISTENT
from ..state import STATE_PRESENT, STATE_FLAG_NONRECOVERABLE, STATE_FLAG_INITIAL, STATE_ABSENT, STATE_RUNNING
from .base import AbstractActionGenerator
from . import (InstanceAction, DERIVED_ACTION_STARTUP, DERIVED_ACTION_RELAUNCH, ACTION_START,
               UTIL_ACTION_PREPARE_CONTAINER, DERIVED_ACTION_RESET, UTIL_ACTION_EXEC_ALL)


class ResumeActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        Attached containers are created and prepared, if they are missing. They are re-created if they have terminated
        with errors. Instance containers are created if missing, started if stopped, and re-created / started if an
        attached container has been missing.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)
        attached_actions = []
        recreate_attached = False
        for attached_state in states.attached:
            if attached_state.base_state == STATE_ABSENT:
                action = DERIVED_ACTION_STARTUP
                recreate_attached = True
            else:
                if attached_state.flags & STATE_FLAG_NONRECOVERABLE:
                    action = DERIVED_ACTION_RELAUNCH
                    recreate_attached = True
                elif attached_state.flags & STATE_FLAG_INITIAL:
                    action = ACTION_START
                else:
                    continue
            attached_actions.append(new_action(attached_state.instance, action))
            attached_actions.append(new_action(attached_state.instance, UTIL_ACTION_PREPARE_CONTAINER))

        instance_actions = []
        if recreate_attached:
            for instance_state in states.instances:
                if instance_state.base_state == STATE_ABSENT:
                    action = DERIVED_ACTION_STARTUP
                elif instance_state.base_state == STATE_RUNNING:
                    action = DERIVED_ACTION_RESET
                elif instance_state.base_state == STATE_PRESENT:
                    if instance_state.base_state & STATE_FLAG_INITIAL:
                        action = ACTION_START
                    else:
                        action = DERIVED_ACTION_RELAUNCH
                else:
                    continue
                instance_actions.append(new_action(instance_state.instance, action))
                instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_ALL))
        else:
            for instance_state in states.instances:
                if instance_state.base_state == STATE_ABSENT:
                    action = DERIVED_ACTION_STARTUP
                else:
                    if instance_state.flags & STATE_FLAG_NONRECOVERABLE:
                        action = DERIVED_ACTION_RESET
                    elif (instance_state.base_state != STATE_RUNNING and
                          (instance_state.flags & STATE_FLAG_INITIAL or not states.flags & CONFIG_FLAG_PERSISTENT)):
                        action = ACTION_START
                    else:
                        continue
                instance_actions.append(new_action(instance_state.instance, action))
                instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_ALL))

        return attached_actions, instance_actions
