# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from dockermap.map.state import STATE_FLAG_RESTARTING
from ..policy import CONFIG_FLAG_DEPENDENT
from ..state import STATE_ABSENT, STATE_RUNNING, STATE_PRESENT
from .resume import ResumeActionGenerator
from . import InstanceAction, ACTION_REMOVE, DERIVED_ACTION_SHUTDOWN, UTIL_ACTION_SCRIPT


class ScriptActionException(Exception):
    pass


class ScriptActionGenerator(ResumeActionGenerator):
    remove_existing_before = False
    policy_options = ['remove_existing_before']

    def get_state_actions(self, states):
        """
        :param states: Configuration states.
        :type states: dockermap.map.state.ContainerConfigStates
        :return: List of attached actions and list of instance actions.
        :rtype: (list[dockermap.map.action.InstanceAction], list[dockermap.map.action.InstanceAction])
        """
        if states.flags & CONFIG_FLAG_DEPENDENT:
            return super(ScriptActionGenerator, self).get_state_actions(states)

        new_action = InstanceAction.config_partial(states.client, states.map, states.config)

        existing = [
            (i, instance_state)
            for i, instance_state in enumerate(states.instances)
            if instance_state.base_state != STATE_ABSENT
        ]
        instance_actions = []
        if existing:
            if self.remove_existing_before:
                for i, state in existing:
                    if state.base_state == STATE_RUNNING or state.flags & STATE_FLAG_RESTARTING:
                        instance_actions.append(new_action(state.instance, DERIVED_ACTION_SHUTDOWN))
                    elif state == STATE_PRESENT:
                        instance_actions.append(new_action(state.instance, ACTION_REMOVE))
            else:
                instance_state = existing[0][1]
                c_name = self._policy.cname(states.map, states.config, instance_state.instance)
                if states.client == self._policy.get_default_client_name():
                    error_msg = "Container {0} existed prior to running the script.".format(c_name)
                else:
                    error_msg = ("Container {0} existed on client {1} prior to running the "
                                 "script.").format(c_name, states.client)
                raise ScriptActionException(error_msg)

        attached_actions = super(ScriptActionGenerator, self).get_state_actions(states)[0]
        instance_actions.append(new_action(UTIL_ACTION_SCRIPT))
        return attached_actions, instance_actions
