# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import posixpath

from requests import Timeout
import six


class ScriptRunException(Exception):
    pass


class ScriptMixin(object):
    remove_existing_before = False
    remove_created_after = True

    def run_script(self, map_name, container, instance=None, script_path=None, entrypoint=None,
                   command_format=None, wait_timeout=None, container_script_dir='/tmp/script_run', timestamps=None,
                   tail='all'):
        """
        Creates a container from its configuration to run a script or single command. The container is specifically
        created for this action. If it exists prior to the script run, it fails; optionally it can be removed by setting
        :attr:`remove_existing_before` to ``True``. The script is run by setting entrypoint and command and
        mounting the directory containing the script to the new container. After the script run, the container is
        destroyed (excluding its dependencies), unless :attr:`remove_created_after` is set to ``False``.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instance: Optional instance to use for running the script.
        :type instance: unicode | str
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
        c_name = self.cname(map_name, container, instance)
        c_map = self.container_maps[map_name]
        c_config = c_map.get_existing(container)
        config_clients = {client_name: (client, client_config)
                          for client_name, client, client_config in self.get_clients(c_config, c_map)}
        instances = [instance] if instance else None

        if self.remove_existing_before:
            # Remove container if it exists.
            self.shutdown_actions(map_name, container, instances)
        else:
            # Check if containers exist prior to any action.
            for client_name in config_clients.keys():
                if c_name in self.container_names[client_name]:
                    if client_name == self.get_default_client_name():
                        error_msg = "Container {0} existed prior to running the script.".format(c_name, client_name)
                    else:
                        error_msg = ("Container {0} existed on client {1} prior to running the "
                                     "script.").format(c_name, client_name)
                    raise ScriptRunException(error_msg)

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
        new_containers = self.create_actions(map_name, container, instances, entrypoint=entrypoint, command=command,
                                             volumes=volumes, host_config=dict(binds=binds))
        if not new_containers:
            raise ScriptRunException("No new containers were created.")
        results = {}
        try:
            self.start_actions(map_name, container, instances, binds=binds)
            for client_name, container_info in new_containers:
                client, client_config = config_clients[client_name]
                timeout = wait_timeout or client_config.get('wait_timeout')
                container_id = container_info['Id']
                try:
                    client.wait(container_id, timeout=timeout)
                except Timeout:
                    results[client_name] = {'id': container_id, 'error': ("Timed out while waiting for the container "
                                                                          "to finish.")}
                else:
                    c_info = client.inspect_container(container_id)
                    exit_code = c_info['State']['ExitCode']
                    log_str = client.logs(container_id, timestamps=timestamps, tail=tail)
                    results[client_name] = {'id': container_id, 'log': log_str, 'exit_code': exit_code}
        finally:
            if self.remove_created_after:
                self.shutdown_actions(map_name, container, instances)
        return results
