# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

import six

from ..input import ItemType
from ..state import State, StateFlags
from . import ItemAction, Action, ContainerUtilAction, VolumeUtilAction, NetworkUtilAction, ImageAction, DerivedAction
from .base import AbstractActionGenerator


log = logging.getLogger(__name__)


class UpdateActionGenerator(AbstractActionGenerator):
    pull_before_update = False
    pull_insecure_registry = False
    policy_options = ['pull_before_update', 'pull_insecure_registry']

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
        if config_type == ItemType.NETWORK:
            if state.base_state == State.ABSENT:
                log.debug("Not found - creating network %s.", config_id)
                return [ItemAction(state, Action.CREATE)]
            elif state.state_flags & StateFlags.NEEDS_RESET:
                log.debug("Found to be outdated - resetting %s.", config_id)
                connected_containers = state.extra_data.get('containers')
                if connected_containers:
                    cc_names = [c_info.get('Name', c_id) for c_id, c_info in six.iteritems(connected_containers)]
                    log.debug("Disconnecting containers from %s: %s.", config_id, cc_names)
                    actions = [ItemAction(state, NetworkUtilAction.DISCONNECT_ALL, containers=cc_names)]
                else:
                    actions = []
                actions.append(ItemAction(state, DerivedAction.RESET_NETWORK))
                return actions
        elif config_type == ItemType.IMAGE:
            if state.base_state == State.ABSENT or self.pull_before_update:
                return [ItemAction(state, ImageAction.PULL,
                                   insecure_registry=self.pull_insecure_registry)]
        elif config_type == ItemType.VOLUME:
            if state.base_state == State.ABSENT:
                log.debug("Not found - creating attached volume %s.", config_id)
                action_type = Action.CREATE
            elif state.state_flags & StateFlags.NEEDS_RESET:
                log.debug("Found to be outdated or non-recoverable - resetting %s.", config_id)
                action_type = DerivedAction.RESET_VOLUME
            elif state.state_flags & StateFlags.INITIAL:
                log.debug("Container for attached volume found but initial, starting %s.", config_id)
                action_type = Action.START
            else:
                return None
            return [
                ItemAction(state, action_type),
                ItemAction(state, VolumeUtilAction.PREPARE),
            ]
        elif config_type == ItemType.CONTAINER:
            ci_initial = state.state_flags & StateFlags.INITIAL
            if state.base_state == State.ABSENT:
                log.debug("Not found - creating and starting instance container %s.", config_id)
                action_type = DerivedAction.STARTUP_CONTAINER
            elif state.state_flags & StateFlags.NEEDS_RESET:
                if state.base_state == State.RUNNING or state.state_flags & StateFlags.RESTARTING:
                    log.debug("Found to be outdated or non-recoverable - resetting %s.", config_id)
                    action_type = DerivedAction.RESET_CONTAINER
                else:
                    log.debug("Found to be outdated or non-recoverable - relaunching %s.", config_id)
                    action_type = DerivedAction.RELAUNCH_CONTAINER
            else:
                actions = []
                if state.state_flags & StateFlags.NETWORK_DISCONNECTED:
                    dn = state.extra_data['disconnected']
                    log.debug("Container is connecting to the following networks: %s.", dn)
                    actions.append(ItemAction(state, Action.CONNECT, endpoints=dn))
                if state.state_flags & StateFlags.NETWORK_MISMATCH:
                    rn = state.extra_data['reconnect']
                    n_names, n_ep = zip(*rn)
                    log.debug("Container is reconnecting to the following networks: %s.", n_names)
                    actions.extend([
                        ItemAction(state, Action.DISCONNECT, networks=n_names),
                        ItemAction(state, Action.CONNECT, endpoints=n_ep),
                    ])
                if state.state_flags & StateFlags.NETWORK_LEFT:
                    ln = state.extra_data['left']
                    log.debug("Container is disconnecting from the following networks: %s.", ln)
                    actions.append(ItemAction(state, Action.DISCONNECT, networks=ln))
                if (state.base_state != State.RUNNING and
                        (ci_initial or not state.state_flags & StateFlags.PERSISTENT)):
                    log.debug("Container found but not running, starting %s.", config_id)
                    actions.extend([
                        ItemAction(state, Action.START),
                        ItemAction(state, ContainerUtilAction.EXEC_ALL),
                    ])
                else:
                    if state.state_flags & StateFlags.EXEC_COMMANDS:
                        run_cmds = state.extra_data['exec_commands']
                        if run_cmds:
                            log.debug("Container %s up-to-date, but with missing commands %s.", config_id, run_cmds)
                            actions.append(ItemAction(state, ContainerUtilAction.EXEC_COMMANDS, run_cmds=run_cmds))
                return actions
            return [
                ItemAction(state, action_type),
                ItemAction(state, ContainerUtilAction.EXEC_ALL),
            ]
