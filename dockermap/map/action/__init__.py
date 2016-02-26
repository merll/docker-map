# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from six import string_types, python_2_unicode_compatible

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


def _action_type_list(value):
    if isinstance(value, list):
        return value
    elif isinstance(value, tuple):
        return list(value)
    elif isinstance(value, string_types):
        return [value]
    elif value:
        raise ValueError("String or list must be provided for 'action_types'. Found {0}.".format(
                type(value).__name__))
    return []


@python_2_unicode_compatible
class InstanceAction(object):
    """
    Utility class for storing container actions.

    :param client_name: Client configuration name.
    :type client_name: unicode | str
    :param map_name: Container map name.
    :type map_name: unicode | str
    :param config_name: Container configuration name.
    :type config_name: unicode | str
    :param instance_name: Instance name.
    :type instance_name: unicode | str
    :param action_types: Action type name(s) to perform. Input is converted to a list.
    :type action_types: unicode | str | list[unicode | str] | tuple[unicode | str]
    :param extra_data: Extra data. Typically passed on as keyword arguments to the client function.
    :type extra_data: dict
    :param kwargs: Addtional keyword arguments; added to extra_data
    """
    def __init__(self, client_name, map_name, config_name, instance_name, action_types=None, extra_data=None, **kwargs):
        self._client = client_name
        self._map = map_name
        self._config = config_name
        self._instance = instance_name
        self._action_types = _action_type_list(action_types)
        self._extra_data = extra_data.copy() if extra_data else {}
        self._extra_data.update(kwargs)

    def __str__(self):
        return ("InstanceAction(client={0._client!r}, map={0._map!r}, config={0._config!r}, instance={0._instance!r}, "
                "action_types={0._action_types!r}, extra_data={0._extra_data!r})".format(self))

    __repr__ = __str__

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
        """
        Tuple of client name, map name, and container configuration name.

        :return: Tuple with aforementioned aliases.
        :rtype: (unicode | str, unicode | str, unicode | str)
        """
        return self._client, self._map, self._config

    @property
    def instance_tuple(self):
        """
        Tuple of client name, map name, container configuration name, and instance.

        :return: Tuple with aforementioned aliases.
        :rtype: (unicode | str, unicode | str, unicode | str, unicode | str)
        """
        return self._client, self._map, self._config, self._instance

    @property
    def action_types(self):
        """
        Action type name(s) to perform. Input is converted to a list.

        :return: Action type(s).
        :rtype: list[unicode | str]
        """
        return self._action_types

    @action_types.setter
    def action_types(self, value):
        self._action_types = _action_type_list(value)

    @property
    def extra_data(self):
        """
        Extra data. Typically passed on as keyword arguments to the client function.

        :return: Dictionary with extra data.
        :rtype: dict
        """
        return self._extra_data

    @extra_data.setter
    def extra_data(self, value):
        self._extra_data = value
