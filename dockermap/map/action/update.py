# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_VOLUME, ITEM_TYPE_NETWORK
from ..policy import ConfigFlags
from ..state import STATE_ABSENT, STATE_RUNNING, StateFlags
from .base import AbstractActionGenerator
from . import (ItemAction, ACTION_CREATE, ACTION_START, ACTION_CONNECT, ACTION_DISCONNECT,
               C_UTIL_ACTION_EXEC_ALL, C_UTIL_ACTION_EXEC_COMMANDS,
               N_UTIL_ACTION_DISCONNECT_ALL, V_UTIL_ACTION_PREPARE,
               DERIVED_ACTION_RESET_CONTAINER, DERIVED_ACTION_STARTUP_CONTAINER, DERIVED_ACTION_STARTUP_VOLUME,
               DERIVED_ACTION_RELAUNCH_CONTAINER, DERIVED_ACTION_RELAUNCH_VOLUME, DERIVED_ACTION_RESET_NETWORK,
               DERIVED_ACTION_RESET_VOLUME)


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
            if state.base_state == STATE_ABSENT:
                log.debug("Not found - creating network %s.", config_id)
                return [ItemAction(state, ACTION_CREATE)]
            elif state.state_flags & StateFlags.NEEDS_RESET:
                log.debug("Found to be outdated - resetting %s.", config_id)
                connected_containers = state.extra_data.get('containers')
                if connected_containers:
                    cc_names = [c.get('Name', c['Id']) for c in connected_containers]
                    log.debug("Disconnecting containers from %s: %s.", config_id, cc_names)
                    actions = [ItemAction(state, N_UTIL_ACTION_DISCONNECT_ALL, containers=cc_names)]
                else:
                    actions = []
                actions.append(ItemAction(state, DERIVED_ACTION_RESET_NETWORK))
                return actions
        elif config_type == ITEM_TYPE_VOLUME:
            # TODO: To be changed for Docker volumes.
            if state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting attached container %s.", config_id)
                action_type = DERIVED_ACTION_STARTUP_VOLUME
            elif state.state_flags & StateFlags.NEEDS_RESET:
                if state.base_state == STATE_RUNNING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", config_id)
                    action_type = DERIVED_ACTION_RESET_VOLUME
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", config_id)
                    action_type = DERIVED_ACTION_RELAUNCH_VOLUME
            elif state.state_flags & StateFlags.INITIAL:
                log.debug("Container found but initial, starting %s.", config_id)
                action_type = ACTION_START
            else:
                return None
            return [
                ItemAction(state, action_type),
                ItemAction(state, V_UTIL_ACTION_PREPARE),
            ]
        elif config_type == ITEM_TYPE_CONTAINER:
            ci_initial = state.state_flags & StateFlags.INITIAL
            if state.base_state == STATE_ABSENT:
                log.debug("Not found - creating and starting instance container %s.", config_id)
                action_type = DERIVED_ACTION_STARTUP_CONTAINER
            elif state.state_flags & StateFlags.NEEDS_RESET:
                if state.base_state == STATE_RUNNING or state.state_flags & StateFlags.RESTARTING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", config_id)
                    action_type = DERIVED_ACTION_RESET_CONTAINER
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", config_id)
                    action_type = DERIVED_ACTION_RELAUNCH_CONTAINER
            else:
                actions = []
                if state.state_flags & StateFlags.NETWORK_DISCONNECTED:
                    dn = state.extra_data['disconnected']
                    log.debug("Container is connecting to the following networks: %s.", dn)
                    actions.append(ItemAction(state, ACTION_CONNECT, endpoints=dn))
                if state.state_flags & StateFlags.NETWORK_MISMATCH:
                    rn = state.extra_data['reconnect']
                    n_names, n_ep = zip(*rn)
                    log.debug("Container is reconnecting to the following networks: %s.", n_names)
                    actions.extend([
                        ItemAction(state, ACTION_DISCONNECT, networks=n_names),
                        ItemAction(state, ACTION_CONNECT, endpoints=n_ep),
                    ])
                if state.state_flags & StateFlags.NETWORK_LEFT:
                    ln = state.extra_data['left']
                    log.debug("Container is disconnecting to the following networks: %s.", ln)
                    actions.append(ItemAction(state, ACTION_DISCONNECT, networks=ln))
                if (state.base_state != STATE_RUNNING and
                        (ci_initial or not state.config_flags & ConfigFlags.CONTAINER_PERSISTENT)):
                    log.debug("Container found but not running, starting %s.", config_id)
                    actions.extend([
                        ItemAction(state, ACTION_START),
                        ItemAction(state, C_UTIL_ACTION_EXEC_ALL),
                    ])
                else:
                    if state.state_flags & StateFlags.EXEC_COMMANDS:
                        run_cmds = state.extra_data['exec_commands']
                        if run_cmds:
                            log.debug("Container %s up-to-date, but with missing commands %s.", config_id, run_cmds)
                            actions.append(ItemAction(state, C_UTIL_ACTION_EXEC_COMMANDS, run_cmds=run_cmds))
                return actions
            return [
                ItemAction(state, action_type),
                ItemAction(state, C_UTIL_ACTION_EXEC_ALL),
            ]
