# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import posixpath

from requests import Timeout
import six

from ..action import UTIL_ACTION_SCRIPT


class ScriptRunException(Exception):
    pass


class ScriptMixin(object):
    instance_action_method_names = [
        (UTIL_ACTION_SCRIPT, 'run_script'),
    ]
    remove_created_after = True

    def run_script(self, client, config, c_name, script_path=None, entrypoint=None, command_format=None,
                   wait_timeout=None, container_script_dir='/tmp/script_run', timestamps=None, tail='all'):
        """
        Creates a container from its configuration to run a script or single command. The container is specifically
        created for this action. If it exists prior to the script run, it fails; optionally it can be removed by setting
        :attr:`remove_existing_before` to ``True``. The script is run by setting entrypoint and command and
        mounting the directory containing the script to the new container. After the script run, the container is
        destroyed (excluding its dependencies), unless :attr:`remove_created_after` is set to ``False``.

        :param client: Docker client.
        :type client: docker.Client
        :param config: Configuration.
        :type config: dockermap.map.runner.base.ActionConfig
        :param c_name: Container name.
        :type c_name: unicode | str
        :param script_path: Path to the script on the Docker host. Note that this needs to have the executable bit
         set, if the script runtime (e.g. bash) requires it. If no script is to be used, (e.g. for a single command),
         this can point to a directory for writing back results to.
        :param entrypoint: Entrypoint of the container. Typically this should be the scripting executable, such as
         ``/bin/bash``.
        :type entrypoint: unicode | str
        :param command_format: Command to pass to the container. This should be any arguments to the entrypoint, and
         can include a formatting string variable ``{script_path}`` which is substituted with the path inside the
         container. The command_format can be provided as a single string or a list of strings. Of no command is set,
         ``['-c', '{script_path}']`` is assumed, which are the arguments to ``/bin/bash`` for running a single script.
        :type command_format: unicode | str | list[unicode | str] | tuple[unicode | str]
        :param wait_timeout: How long to wait for the container to finish. If not set, will be read from the client
         configuration parameter ``wait_timeout``.
        :type wait_timeout: int
        :param container_script_dir: Directory to use for the script inside the container. This is also the path where
         other files in the same directory as the script will be located.
        :type container_script_dir: unicode | str
        :param timestamps:
        :type timestamps: bool
        :param tail:
        :type tail: unicode | str
        :return: A dictionary with the client names as keys, and the results as values. The results are a nested
         dictionary with the container ``id``, the stdout output ``log``, and the exit code ``exit_code``. In case
         a wait timeout occurred, instead of ``log`` and ``exit_code`` returns a key ``error``.
        :rtype: dict[unicode | str, dict]
        """
        client_config = config.client_config
        client_timeout = client_config.get('timeout')
        use_host_config = client_config.get('use_host_config')
        if script_path:
            if os.path.isdir(script_path):
                script_dir = script_path
                c_script_path = container_script_dir
            else:
                script_dir, script_name = os.path.split(script_path)
                c_script_path = posixpath.join(container_script_dir, script_name)
            if command_format:
                if isinstance(command_format, (tuple, list)):
                    command = [six.text_type(cmd_item).format(script_path=c_script_path) for cmd_item in command_format]
                elif isinstance(command_format, six.string_types):
                    command = command_format.format(script_path=c_script_path)
                else:
                    raise ValueError("Only strings and lists of strings are allowed as a command.")
            else:
                command = None
            volumes = [container_script_dir]
            binds = {script_dir: dict(bind=container_script_dir, ro=False)}
        else:
            volumes = None
            binds = None
            command = command_format

        if use_host_config:
            create_extra_kwargs = {'host_config': dict(binds=binds)}
            start_extra_kwargs = {}
        else:
            create_extra_kwargs = {}
            start_extra_kwargs = {'binds': binds}
        created = self.create_instance(client, config, c_name, entrypoint=entrypoint, command=command,
                                       volumes=volumes, **create_extra_kwargs)
        if not created:
            raise ScriptRunException("No new containers were created.")
        try:
            self.start_instance(client, config, c_name, **start_extra_kwargs)
            timeout = wait_timeout or client_config.get('wait_timeout') or client_timeout
            container_id = created['Id']
            try:
                self.wait_instance(client, config, c_name, timeout=timeout)
            except Timeout:
                result = {'id': container_id, 'error': "Timed out while waiting for the container to finish."}
            else:
                c_info = client.inspect_container(container_id)
                exit_code = c_info['State']['ExitCode']
                log_str = client.logs(container_id, timestamps=timestamps, tail=tail)
                result = {'id': container_id, 'log': log_str, 'exit_code': exit_code}
        finally:
            if self.remove_created_after:
                self.stop_instance(client, config, c_name, timeout=1)
                self.remove_instance(client, config, c_name)
        return result
