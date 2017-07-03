# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple

from six import string_types, python_2_unicode_compatible

ITEM_TYPE_CONTAINER = 'container'
ITEM_TYPE_VOLUME = 'volume'
ITEM_TYPE_NETWORK = 'network'

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
UTIL_ACTION_PREPARE_VOLUME = 'prepare_volume'               # Set up attached volume permissions.

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


ClientMapActions = namedtuple('ClientMapActions', ['client_name', 'map_name', 'actions'])


@python_2_unicode_compatible
class ItemAction(object):
    """
    Utility class for storing actions.

    :param config_type: Configuration item type.
    :type config_type: unicode | str
    :param config_name: Configuration name.
    :type config_name: unicode | str
    :param instance_name: Instance name.
    :type instance_name: unicode | str
    :param action_types: Action type name(s) to perform. Input is converted to a list.
    :type action_types: unicode | str | list[unicode | str] | tuple[unicode | str]
    :param extra_data: Extra data. Typically passed on as keyword arguments to the client function.
    :type extra_data: dict
    :param kwargs: Additional keyword arguments; added to extra_data
    """
    def __init__(self, config_type, config_name, instance_name=None, action_types=None, extra_data=None, **kwargs):
        self._config_type = config_type
        self._config = config_name
        self._instance = instance_name
        self._action_types = _action_type_list(action_types)
        self._extra_data = extra_data.copy() if extra_data else {}
        self._extra_data.update(kwargs)

    def __str__(self):
        return ("InstanceAction(config_type={0._config_type!r}, client={0._client!r}, map={0._map!r}, "
                "config={0._config!r}, instance={0._instance!r}, action_types={0._action_types!r}, "
                "extra_data={0._extra_data!r})".format(self))

    __repr__ = __str__

    @property
    def config_type(self):
        """
        The configuration item type, e.g. container, network, or volume.

        :return: Configuration item type.
        :rtype: unicode | str
        """
        return self._config_type

    @property
    def config_name(self):
        """
        The configuration name with the information to apply to the action.

        :return: Configuration name.
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
