# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..input import EXEC_POLICY_INITIAL
from ..state import (STATE_FLAG_NONRECOVERABLE, STATE_ABSENT, STATE_FLAG_INITIAL, STATE_RUNNING, STATE_FLAG_OUTDATED,
                     STATE_FLAG_RESTARTING)
from .base import AbstractActionGenerator
from . import (ACTION_START, UTIL_ACTION_EXEC_ALL, UTIL_ACTION_EXEC_COMMANDS, DERIVED_ACTION_RESET,
               DERIVED_ACTION_STARTUP, DERIVED_ACTION_RELAUNCH, UTIL_ACTION_PREPARE_CONTAINER, InstanceAction,
               ACTION_STOP, UTIL_ACTION_SIGNAL_STOP)


log = logging.getLogger(__name__)


class UpdateActionGenerator(AbstractActionGenerator):
    stop_dependent_before = False

    def expand_instance_actions(self, actions):
        """

        :param actions: Action list to expand.
        :type actions: list[dockermap.map.action.InstanceAction]
        :return: __generator[dockermap.map.action.InstanceAction]
        """
        if self.stop_dependent_before:
            for action in super(UpdateActionGenerator, self).expand_instance_actions(actions):
                if action.action_type in (ACTION_STOP, UTIL_ACTION_SIGNAL_STOP):
                    # Anticipate the stop of a dependency container by stopping all dependents first.
                    dependent = self._policy.get_dependents(action.map_name, action.config_name)
                    for d_map_name, d_config_name, d_instance in dependent:
                        log.debug("Stopping dependent container %s.%s instance %s.", d_map_name, d_config_name,
                                  d_instance or '<default>')
                        d_map = self._policy.container_maps[d_map_name]
                        d_config = d_map.get_existing(d_config_name)
                        stop_action_type = UTIL_ACTION_SIGNAL_STOP if d_config.stop_signal else ACTION_STOP
                        yield InstanceAction(action.client_name, d_map_name, d_config_name, d_instance,
                                             stop_action_type)
                yield action
        else:
            for action in super(UpdateActionGenerator, self).expand_instance_actions(actions):
                yield action

    def get_state_actions(self, states):
        """

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)
        log.debug("Evaluating containers for client: %s, map: %s, config: %s.", states.client, states.map,
                  states.config)
        attached_actions = []
        for attached_state in states.attached:
            log.debug("Evaluating attached container %s.", attached_state.instance)
            if attached_state.flags == STATE_ABSENT:
                log.debug("Not found - creating and starting attached container %s.", attached_state.instance)
                action = DERIVED_ACTION_STARTUP
            elif attached_state.flags & STATE_FLAG_INITIAL:
                log.debug("Container found but initial, starting %s.", attached_state.instance)
                action = ACTION_START
            elif attached_state.flags & (STATE_FLAG_NONRECOVERABLE | STATE_FLAG_OUTDATED):
                if attached_state.base_state == STATE_RUNNING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", attached_state.instance)
                    action = DERIVED_ACTION_RESET
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", attached_state.instance)
                    action = DERIVED_ACTION_RELAUNCH
            else:
                continue
            attached_actions.append(new_action(attached_state.instance, action))
            attached_actions.append(new_action(attached_state.instance, UTIL_ACTION_PREPARE_CONTAINER))

        instance_actions = []
        for instance_state in states.instances:
            instance_name = instance_state.instance or '<default>'
            log.debug("Evaluating container instance %s.", instance_name)
            ci_initial = instance_state.flags & STATE_FLAG_INITIAL
            if instance_state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting attached container %s.", instance_name)
                action = DERIVED_ACTION_STARTUP
            elif ci_initial:
                log.debug("Container found but initial, starting %s.", instance_name)
                action = ACTION_START
            elif instance_state.flags & (STATE_FLAG_NONRECOVERABLE | STATE_FLAG_OUTDATED):
                if instance_state.base_state == STATE_RUNNING or instance_state.flags & STATE_FLAG_RESTARTING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", instance_name)
                    action = DERIVED_ACTION_RESET
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", instance_name)
                    action = DERIVED_ACTION_RELAUNCH
            else:
                run_cmds = [
                    exec_cmd
                    for exec_cmd, running in instance_state.extra_data.get('exec_commands', [])
                    if not running and (ci_initial or exec_cmd.policy != EXEC_POLICY_INITIAL)
                ]
                if run_cmds:
                    instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_COMMANDS,
                                                       run_cmds=run_cmds))
                continue
            instance_actions.append(new_action(instance_state.instance, action))
            instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_ALL))

        return attached_actions, instance_actions
