# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..input import EXEC_POLICY_INITIAL
from ..policy import CONFIG_FLAG_PERSISTENT
from ..state import (STATE_FLAG_NONRECOVERABLE, STATE_ABSENT, STATE_FLAG_INITIAL, STATE_RUNNING, STATE_FLAG_OUTDATED,
                     STATE_FLAG_RESTARTING)
from .base import AbstractActionGenerator
from . import (ACTION_START, UTIL_ACTION_EXEC_ALL, UTIL_ACTION_EXEC_COMMANDS, DERIVED_ACTION_RESET,
               DERIVED_ACTION_STARTUP, DERIVED_ACTION_RELAUNCH, UTIL_ACTION_PREPARE_CONTAINER, InstanceAction)


log = logging.getLogger(__name__)


class UpdateActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, states, **kwargs):
        """
        For attached volumes, missing containers are created and initial containers are started and prepared with
        permissions. Outdated containers or containers with errors are recreated. The latter also applies to instance
        containers. Similarly, instance containers are created if missing and started unless not initial and marked as
        persistent.
        On running instance containers missing exec commands are run; if the container needs to be started, all exec
        commands are launched.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        new_action = InstanceAction.config_partial(states.client, states.map, states.config)
        log.debug("Evaluating containers for client: %s, map: %s, config: %s.", states.client, states.map,
                  states.config)
        attached_actions = []
        for attached_state in states.attached:
            log.debug("Evaluating attached container %s.", attached_state.instance)
            if attached_state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting attached container %s.", attached_state.instance)
                action_type = DERIVED_ACTION_STARTUP
            elif attached_state.flags & (STATE_FLAG_NONRECOVERABLE | STATE_FLAG_OUTDATED):
                if attached_state.base_state == STATE_RUNNING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", attached_state.instance)
                    action_type = DERIVED_ACTION_RESET
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", attached_state.instance)
                    action_type = DERIVED_ACTION_RELAUNCH
            elif attached_state.flags & STATE_FLAG_INITIAL:
                log.debug("Container found but initial, starting %s.", attached_state.instance)
                action_type = ACTION_START
            else:
                continue
            attached_actions.append(new_action(attached_state.instance, action_type))
            attached_actions.append(new_action(attached_state.instance, UTIL_ACTION_PREPARE_CONTAINER))

        instance_actions = []
        for instance_state in states.instances:
            instance_name = instance_state.instance or '<default>'
            log.debug("Evaluating container instance %s.", instance_name)
            ci_initial = instance_state.flags & STATE_FLAG_INITIAL
            if instance_state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting instance container %s.", instance_name)
                action_type = DERIVED_ACTION_STARTUP
            elif instance_state.flags & (STATE_FLAG_NONRECOVERABLE | STATE_FLAG_OUTDATED):
                if instance_state.base_state == STATE_RUNNING or instance_state.flags & STATE_FLAG_RESTARTING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", instance_name)
                    action_type = DERIVED_ACTION_RESET
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", instance_name)
                    action_type = DERIVED_ACTION_RELAUNCH
            elif (instance_state.base_state != STATE_RUNNING and
                  (ci_initial or not states.flags & CONFIG_FLAG_PERSISTENT)):
                log.debug("Container found but not running, starting %s.", instance_name)
                action_type = ACTION_START
            else:
                run_cmds = [
                    exec_cmd
                    for exec_cmd, running in instance_state.extra_data.get('exec_commands', [])
                    if not running and (ci_initial or exec_cmd.policy != EXEC_POLICY_INITIAL)
                ]
                if run_cmds:
                    log.debug("Container %s up-to-date, but with missing commands %s.", instance_name, run_cmds)
                    instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_COMMANDS,
                                                       run_cmds=run_cmds))
                continue
            instance_actions.append(new_action(instance_state.instance, action_type))
            instance_actions.append(new_action(instance_state.instance, UTIL_ACTION_EXEC_ALL))

        return attached_actions, instance_actions
