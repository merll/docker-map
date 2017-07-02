# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..input import EXEC_POLICY_INITIAL
from ..policy import CONTAINER_CONFIG_FLAG_PERSISTENT
from ..state import (STATE_FLAG_NONRECOVERABLE, STATE_ABSENT, STATE_FLAG_INITIAL, STATE_RUNNING, STATE_FLAG_OUTDATED,
                     STATE_FLAG_RESTARTING)
from .base import AbstractActionGenerator
from . import (ItemAction, ClientMapActions, ITEM_TYPE_VOLUME, ITEM_TYPE_CONTAINER, ITEM_TYPE_NETWORK, ACTION_START,
               UTIL_ACTION_EXEC_ALL, UTIL_ACTION_EXEC_COMMANDS, DERIVED_ACTION_RESET, DERIVED_ACTION_STARTUP,
               DERIVED_ACTION_RELAUNCH, UTIL_ACTION_PREPARE_VOLUME)


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
        log.debug("Evaluating containers for state: %s.", states)
        actions = []
        for state in states.volumes:
            log.debug("Evaluating volume or container %s.", state.instance)
            if state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting attached container %s.", state.instance)
                action_type = DERIVED_ACTION_STARTUP
            elif state.state_flags & (STATE_FLAG_NONRECOVERABLE | STATE_FLAG_OUTDATED):
                if state.base_state == STATE_RUNNING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", state.instance)
                    action_type = DERIVED_ACTION_RESET
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", state.instance)
                    action_type = DERIVED_ACTION_RELAUNCH
            elif state.state_flags & STATE_FLAG_INITIAL:
                log.debug("Container found but initial, starting %s.", state.instance)
                action_type = ACTION_START
            else:
                continue
            actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, action_type))
            actions.append(ItemAction(ITEM_TYPE_VOLUME, state.config, state.instance, UTIL_ACTION_PREPARE_VOLUME))

        instance_actions = []
        for state in states.containers:
            instance_name = state.instance or '<default>'
            log.debug("Evaluating container instance %s.", instance_name)
            ci_initial = state.state_flags & STATE_FLAG_INITIAL
            if state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting instance container %s.", instance_name)
                action_type = DERIVED_ACTION_STARTUP
            elif state.state_flags & (STATE_FLAG_NONRECOVERABLE | STATE_FLAG_OUTDATED):
                if state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", instance_name)
                    action_type = DERIVED_ACTION_RESET
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", instance_name)
                    action_type = DERIVED_ACTION_RELAUNCH
            elif (state.base_state != STATE_RUNNING and
                  (ci_initial or not states.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT)):
                log.debug("Container found but not running, starting %s.", instance_name)
                action_type = ACTION_START
            else:
                run_cmds = [
                    exec_cmd
                    for exec_cmd, running in state.extra_data.get('exec_commands', [])
                    if not running and (ci_initial or exec_cmd.policy != EXEC_POLICY_INITIAL)
                ]
                if run_cmds:
                    log.debug("Container %s up-to-date, but with missing commands %s.", instance_name, run_cmds)
                    instance_actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance,
                                                       UTIL_ACTION_EXEC_COMMANDS, run_cmds=run_cmds))
                continue
            actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, action_type))
            actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance, UTIL_ACTION_EXEC_ALL))

        return ClientMapActions(states.client, states.map, actions)
