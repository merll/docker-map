# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from six import python_2_unicode_compatible

from .. import SimpleEnum


class ActionEnum(SimpleEnum):
    pass


class Action(ActionEnum):
    # Base actions provided by client.
    CREATE = 'create'
    START = 'start'
    RESTART = 'restart'
    STOP = 'stop'
    REMOVE = 'remove'
    KILL = 'kill'
    WAIT = 'wait'               # Wait for item to finish.
    UPDATE = 'update'           # Update the configuration of an object in-place.
    CONNECT = 'connect'         # Connect to network.
    DISCONNECT = 'disconnect'   # Disconnect from network.


class ContainerUtilAction(ActionEnum):
    EXEC_COMMANDS = 'exec_single_command'  # Create & start exec certain commands.
    EXEC_ALL = 'exec_all_commands'         # Create & start all configured exec commands
    SCRIPT = 'script'                      # Create & start container, then create & start exec.
    SIGNAL_STOP = 'signal_stop'            # Send signal (kill) & wait.
    CONNECT_ALL = 'connect_all_networks'   # Connect container to all configured networks.


class VolumeUtilAction(ActionEnum):
    PREPARE = 'prepare_volume'             # Set up volume permissions.


class NetworkUtilAction(ActionEnum):
    DISCONNECT_ALL = 'disconnect_all_containers'    # Disconnect all containers from a network.


class ImageAction(ActionEnum):
    PULL = 'pull_image'


class DerivedAction(object):
    STARTUP_CONTAINER = [Action.CREATE, ContainerUtilAction.CONNECT_ALL,
                         Action.START]                                     # Create, connect, & start
    SHUTDOWN_CONTAINER = [ContainerUtilAction.SIGNAL_STOP, Action.REMOVE]  # Stop & remove
    RESET_CONTAINER = [ContainerUtilAction.SIGNAL_STOP, Action.REMOVE,
                       Action.CREATE, ContainerUtilAction.CONNECT_ALL,
                       Action.START]                                       # Stop, remove, create, connect, & start
    RESTART_CONTAINER = [ContainerUtilAction.SIGNAL_STOP, Action.START]    # Stop & restart
    RESET_VOLUME = [Action.REMOVE, Action.CREATE]                          # Remove, create, & start
    RELAUNCH_CONTAINER = [Action.REMOVE, Action.CREATE,
                          ContainerUtilAction.CONNECT_ALL, Action.START]   # Remove, create, connect, & start
    RESET_NETWORK = [Action.REMOVE, Action.CREATE]                         # Remove & re-create


def _action_type_list(value):
    if isinstance(value, ActionEnum):
        return [value]
    if isinstance(value, list):
        return value
    elif isinstance(value, tuple):
        return list(value)
    elif value:
        raise ValueError("ActionEnum or list must be provided for 'action_types'. Found {0}.".format(
                type(value).__name__))
    return []


@python_2_unicode_compatible
class ItemAction(object):
    """
    Utility class for storing actions.

    :param client_name: Client configuration name.
    :type client_name: unicode | str
    :param config_id: Configuration id tuple.
    :type config_id: dockermap.map.input.MapConfigId
    :param action_types: Action type name(s) to perform. Input is converted to a list.
    :type action_types: unicode | str | list[unicode | str] | tuple[unicode | str]
    :param extra_data: Extra data. Typically passed on as keyword arguments to the client function.
    :type extra_data: dict
    :param kwargs: Additional keyword arguments; added to extra_data
    """
    def __init__(self, state, action_types=None, extra_data=None, **kwargs):
        self._state = state
        self._action_types = _action_type_list(action_types)
        self._extra_data = extra_data.copy() if extra_data else {}
        self._extra_data.update(kwargs)

    def __str__(self):
        return ("ItemAction(client_name={0._state.client_name!r}, config_id={0._state.config_id!r}, "
                "action_types={0._action_types!r}, extra_data={0._extra_data!r})".format(self))

    __repr__ = __str__

    @property
    def client_name(self):
        """
        Name of the client configuration affected by this action.

        :return: Client configuration name.
        :rtype: unicode | str
        """
        return self._state.client_name

    @property
    def config_id(self):
        """
        The map configuration id of the affected configuration.

        :return: Configuration id.
        :rtype: dockermap.map.input.MapConfigId
        """
        return self._state.config_id

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
