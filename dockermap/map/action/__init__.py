# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from six import string_types

# Base actions provided by client.
ACTION_CREATE = 'create'
ACTION_START = 'start'
ACTION_RESTART = 'restart'
ACTION_STOP = 'stop'
ACTION_REMOVE = 'remove'
ACTION_KILL = 'kill'
ACTION_WAIT = 'wait'

UTIL_ACTION_EXEC_COMMANDS = 'exec_single_command'           # Create & start exec certain commands.
UTIL_ACTION_EXEC_ALL = 'exec_all_commands'                  # Create & start all configured exec commands
UTIL_ACTION_UPDATE = 'update'                               # Conditional reset or relaunch.
UTIL_ACTION_SCRIPT = 'script'                               # Create & start container, then create & start exec.
UTIL_ACTION_SIGNAL_STOP = 'signal_stop'                     # Send signal (kill) & wait.
UTIL_ACTION_PREPARE_CONTAINER = 'prepare_container'         # Set up attached volume permissions.

DERIVED_ACTION_STARTUP = [ACTION_CREATE, ACTION_START]                            # Create & start
DERIVED_ACTION_SHUTDOWN = [UTIL_ACTION_SIGNAL_STOP, ACTION_REMOVE]                # Stop & remove
DERIVED_ACTION_RESET = [UTIL_ACTION_SIGNAL_STOP, ACTION_REMOVE,
                        ACTION_CREATE, ACTION_START]                              # Stop, remove, create, & start
DERIVED_ACTION_RELAUNCH = [ACTION_REMOVE, ACTION_CREATE, ACTION_START]            # Remove, create, & start


class InstanceAction(object):
    def __init__(self, client_name, map_name, config_name, instance_name, action_types=None, extra_data=None, **kwargs):
        self._client = client_name
        self._map = map_name
        self._config = config_name
        self._instance = instance_name
        self._action_types = []
        self.action_types = action_types
        self._extra_data = extra_data or {}
        self._extra_data.update(kwargs)

    @classmethod
    def config_partial(cls, client_name, map_name, config_name):
        """
        Generates and returns a partial function for creating a series of :class:`InstanceAction` objects with identical
        client, map, config names, but different instance descriptions, action type, and extra arguments.

        :param client_name: Client config name.
        :type client_name: unicode | str
        :param map_name: Container map name.
        :type map_name: unicode | str
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :return: Function with arguments ``instance_name`, ``action_type``, and ``extra_data``.
        :rtype: (unicode | str, unicode | str, dict) -> InstanceAction
        """
        def _new_instance(instance_name, action_types=None, extra_data=None, **kwargs):
            return cls(client_name, map_name, config_name, instance_name,
                       action_types=action_types, extra_data=extra_data, **kwargs)

        return _new_instance

    @property
    def client_name(self):
        """
        The client config name for the action to be performed on.

        :return: Client config name.
        :rtype: unicode | str
        """
        return self._client

    @property
    def map_name(self):
        """
        The container map name containing the container configuration.

        :return: Container map name.
        :rtype: unicode | str
        """
        return self._map

    @property
    def config_name(self):
        """
        The container configuration name with the information to apply to the action.

        :return: Container configuration name.
        :rtype: unicode | str
        """
        return self._config

    @property
    def instance_name(self):
        """
        The container instance name, that belongs to a container configuration. Can be ``None``
        for the default instance.

        :return: Container instance name.
        :rtype: unicode | str | NoneType
        """
        return self._instance

    @property
    def config_tuple(self):
        return self._client, self._map, self._config

    @property
    def instance_tuple(self):
        return self._client, self._map, self._config, self._instance

    @property
    def action_types(self):
        return self._action_types

    @action_types.setter
    def action_types(self, value):
        if isinstance(value, list):
            self._action_types = value
        elif isinstance(value, string_types):
            self._action_types = [value]
        elif value:
            raise ValueError("String or list must be provided for 'action_types'. Found {0}.".format(
                    type(value).__name__))
        else:
            self._action_types = []

    @property
    def extra_data(self):
        return self._extra_data

    @extra_data.setter
    def extra_data(self, value):
        self._extra_data = value
