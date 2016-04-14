# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..action import UTIL_ACTION_EXEC_ALL, UTIL_ACTION_EXEC_COMMANDS

log = logging.getLogger(__name__)


class ExecMixin(object):
    """
    Utility mixin for executing configured commands inside containers.
    """
    instance_action_method_names = [
        (UTIL_ACTION_EXEC_COMMANDS, 'exec_commands'),
        (UTIL_ACTION_EXEC_ALL, 'exec_container_commands'),
    ]

    def exec_commands(self, config, c_name, run_cmds, **kwargs):
        """
        Runs a single command inside a container.

        :param config: Configuration.
        :type config: dockermap.map.runner.ActionConfig
        :param c_name: Container name.
        :type c_name: unicode | str
        :param run_cmds: Commands to run.
        :type run_cmds: list[dockermap.map.input.ExecCommand]
        """
        client = config.client
        for run_cmd in run_cmds:
            cmd = run_cmd.cmd
            cmd_user = run_cmd.user
            log.debug("Creating exec command in container %s with user %s: %s.", c_name, cmd_user, cmd)
            ec_kwargs = self.get_exec_create_kwargs(config, c_name, cmd, cmd_user)
            e_id = client.exec_create(**ec_kwargs)['Id']
            log.debug("Starting exec command with id %s.", e_id)
            es_kwargs = self.get_exec_start_kwargs(config, c_name, e_id)
            client.exec_start(**es_kwargs)

    def exec_container_commands(self, config, c_name, **kwargs):
        """
        Runs all configured commands of a container configuration inside the container instance.

        :param config: Configuration.
        :type config: dockermap.map.runner.ActionConfig
        :param c_name: Container name.
        :type c_name: unicode | str
        """
        config_cmds = config.container_config.exec_commands
        if not config_cmds:
            return
        self.exec_commands(config, c_name, run_cmds=config_cmds)
