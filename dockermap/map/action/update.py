# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..input import EXEC_POLICY_INITIAL, ITEM_TYPE_CONTAINER, ITEM_TYPE_VOLUME, ITEM_TYPE_NETWORK
from ..policy import CONTAINER_CONFIG_FLAG_PERSISTENT
from ..state import STATE_ABSENT, STATE_FLAG_INITIAL, STATE_RUNNING, STATE_FLAG_RESTARTING, STATE_FLAG_NEEDS_RESET
from .base import AbstractActionGenerator
from . import (ItemAction, ACTION_START, UTIL_ACTION_EXEC_ALL, UTIL_ACTION_EXEC_COMMANDS,
               DERIVED_ACTION_RESET, DERIVED_ACTION_STARTUP, DERIVED_ACTION_RELAUNCH, UTIL_ACTION_PREPARE_VOLUME,
               ACTION_CREATE)


log = logging.getLogger(__name__)


class UpdateActionGenerator(AbstractActionGenerator):
    def get_state_actions(self, state, **kwargs):
        """
        For attached volumes, missing containers are created and initial containers are started and prepared with
        permissions. Outdated containers or containers with errors are recreated. The latter also applies to instance
        containers. Similarly, instance containers are created if missing and started unless not initial and marked as
        persistent.
        On running instance containers missing exec commands are run; if the container needs to be started, all exec
        commands are launched.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        config_id = state.config_id
        config_type = config_id.config_type
        if config_type == ITEM_TYPE_NETWORK:
            # TODO: Complete
            if state.base_state == STATE_ABSENT:
                log.debug("Not found - creating network %s.", config_id)
                return [ItemAction(state, ACTION_CREATE)]
        elif config_type == ITEM_TYPE_VOLUME:
            if state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting attached container %s.", config_id)
                action_type = DERIVED_ACTION_STARTUP
            elif state.state_flags & STATE_FLAG_NEEDS_RESET:
                if state.base_state == STATE_RUNNING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", config_id)
                    action_type = DERIVED_ACTION_RESET
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", config_id)
                    action_type = DERIVED_ACTION_RELAUNCH
            elif state.state_flags & STATE_FLAG_INITIAL:
                log.debug("Container found but initial, starting %s.", config_id)
                action_type = ACTION_START
            else:
                return None
            return [
                ItemAction(state, action_type),
                ItemAction(state, UTIL_ACTION_PREPARE_VOLUME),
            ]
        elif config_type == ITEM_TYPE_CONTAINER:
            ci_initial = state.state_flags & STATE_FLAG_INITIAL
            if state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting instance container %s.", config_id)
                action_type = DERIVED_ACTION_STARTUP
            elif state.state_flags & STATE_FLAG_NEEDS_RESET:
                if state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", config_id)
                    action_type = DERIVED_ACTION_RESET
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", config_id)
                    action_type = DERIVED_ACTION_RELAUNCH
            elif (state.base_state != STATE_RUNNING and
                  (ci_initial or not state.config_flags & CONTAINER_CONFIG_FLAG_PERSISTENT)):
                log.debug("Container found but not running, starting %s.", config_id)
                action_type = ACTION_START
            else:
                run_cmds = [
                    exec_cmd
                    for exec_cmd, running in state.extra_data.get('exec_commands', [])
                    if not running and (ci_initial or exec_cmd.policy != EXEC_POLICY_INITIAL)
                ]
                if run_cmds:
                    log.debug("Container %s up-to-date, but with missing commands %s.", config_id, run_cmds)
                    return [ItemAction(state, UTIL_ACTION_EXEC_COMMANDS, run_cmds=run_cmds)]
                return None
            return [
                ItemAction(state, action_type),
                ItemAction(state, UTIL_ACTION_EXEC_ALL),
            ]
