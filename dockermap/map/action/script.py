# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..input import ITEM_TYPE_CONTAINER
from ..policy import CONFIG_FLAG_DEPENDENT
from ..state import STATE_ABSENT, STATE_RUNNING, STATE_FLAG_RESTARTING
from .resume import ResumeActionGenerator
from . import ItemAction, ClientMapActions, ACTION_REMOVE, DERIVED_ACTION_SHUTDOWN, UTIL_ACTION_SCRIPT


log = logging.getLogger(__name__)


class ScriptActionException(Exception):
    pass


class ScriptActionGenerator(ResumeActionGenerator):
    remove_existing_before = False
    policy_options = ['remove_existing_before']

    def get_state_actions(self, states, **kwargs):
        """
        For dependent containers, inherits the behavior from :class:`dockermap.map.action.resume.ResumeActionGenerator`.
        For other the main container, checks if containers exist, and depending on the ``remove_existing_before``
        option either fails or removes them. Otherwise runs the script.

        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: dockermap.map.action.ClientMapActions
        """
        resume_actions = super(ScriptActionGenerator, self).get_state_actions(states, **kwargs)
        if states.config_flags & CONFIG_FLAG_DEPENDENT:
            return resume_actions

        log.debug("Determining script actions for: %s", states)

        existing = [
            state
            for state in states.containers
            if state.base_state != STATE_ABSENT
        ]
        log.debug("Found existing containers: %s", existing)
        actions = [action
                   for action in resume_actions
                   if action.config_type != ITEM_TYPE_CONTAINER]
        if existing:
            if self.remove_existing_before:
                for state in existing:
                    if state.base_state == STATE_RUNNING or state.state_flags & STATE_FLAG_RESTARTING:
                        log.debug("Preparing shutdown of existing container: %s", state.instance)
                        actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, state.instance,
                                                  DERIVED_ACTION_SHUTDOWN))
                    else:
                        log.debug("Preparing removal existing container: %s", state.instance)
                        actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.instance, ACTION_REMOVE))
            else:
                state = existing[0]
                c_name = self._policy.cname(states.map, state.config, state.instance)
                if states.client == self._policy.default_client_name:
                    error_msg = "Container {0} existed prior to running the script.".format(c_name)
                else:
                    error_msg = ("Container {0} existed on client {1} prior to running the "
                                 "script.").format(c_name, states.client)
                raise ScriptActionException(error_msg)

        for state in states.containers:
            actions.append(ItemAction(ITEM_TYPE_CONTAINER, state.config, action_types=UTIL_ACTION_SCRIPT,
                                      extra_data=kwargs))
        return ClientMapActions(states.client, states.map, actions)
