# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..exceptions import ScriptActionException
from ..input import ItemType
from ..policy import ConfigFlags
from ..state import State, StateFlags
from . import ItemAction, Action, ContainerUtilAction, DerivedAction
from .resume import ResumeActionGenerator


log = logging.getLogger(__name__)


class ScriptActionGenerator(ResumeActionGenerator):
    remove_existing_before = False
    policy_options = ['remove_existing_before']

    def get_state_actions(self, state, **kwargs):
        """
        For dependent items, inherits the behavior from :class:`dockermap.map.action.resume.ResumeActionGenerator`.
        For other the main container, checks if containers exist, and depending on the ``remove_existing_before``
        option either fails or removes them. Otherwise runs the script.

        :param state: Configuration state.
        :type state: dockermap.map.state.ConfigState
        :param kwargs: Additional keyword arguments.
        :return: Actions on the client, map, and configurations.
        :rtype: list[dockermap.map.action.ItemAction]
        """
        if state.config_flags & ConfigFlags.DEPENDENT or state.config_id.config_type != ItemType.CONTAINER:
            return super(ScriptActionGenerator, self).get_state_actions(state, **kwargs)

        if state.base_state == State.ABSENT:
            actions = []
        else:
            log.debug("Found existing script containers: %s", state.config_id)
            if not self.remove_existing_before:
                config_id = state.config_id
                c_name = self._policy.cname(config_id.map_name, config_id.config_name, config_id.instance_name)
                if state.client_name == self._policy.default_client_name:
                    error_msg = "Container {0} existed prior to running the script.".format(c_name)
                else:
                    error_msg = ("Container {0} existed on client {1} prior to running the "
                                 "script.").format(c_name, state.client_name)
                raise ScriptActionException(error_msg)

            if state.base_state == State.RUNNING or state.state_flags & StateFlags.RESTARTING:
                log.debug("Preparing shutdown of existing container: %s", state.config_id)
                actions = [ItemAction(state, DerivedAction.SHUTDOWN_CONTAINER)]
            else:
                log.debug("Preparing removal existing container: %s", state.config_id)
                actions = [ItemAction(state, Action.REMOVE)]

        actions.append(ItemAction(state, ContainerUtilAction.SCRIPT, extra_data=kwargs))
        return actions
