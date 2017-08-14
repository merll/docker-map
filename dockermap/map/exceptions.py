# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from ..exceptions import SourceExceptionMixin, PartialResultsMixin


class ActionExceptionMixin(object):
    def __init__(self, config_id, action_type, *args, **kwargs):
        self._config_id = config_id
        self._action_type = action_type
        super(ActionExceptionMixin, self).__init__(*args, **kwargs)

    @property
    def action_type(self):
        """
        Action type on which the error occurred.

        :return: Action type.
        :rtype: dockermap.map.action.ActionEnum
        """
        return self._action_type

    @property
    def config_id(self):
        """
        Configuration id on which the error occurred.

        :return: Configuration id.
        :rtype: dockermap.map.input.MapConfigId
        """
        return self._config_id


class ClientExceptionMixin(object):
    def __init__(self, client_name, *args, **kwargs):
        self._client_name = client_name
        super(ClientExceptionMixin, self).__init__(*args, **kwargs)

    @property
    def client_name(self):
        """
        Client alias where the error occurred.

        :return: Client name.
        :rtype: unicode | str
        """
        return self._client_name


@six.python_2_unicode_compatible
class ActionTypeException(ActionExceptionMixin, Exception):
    def __str__(self):
        return "Invalid action {0} for config type {1}.".format(self._config_id.config_type, self._action_type)

    @property
    def config_id(self):
        """
        Configuration id on which the error occurred.

        :return: Configuration id.
        :rtype: dockermap.map.input.MapConfigId
        """
        return self._config_id

    @property
    def config_type(self):
        """
        Configuration type of where the exception was raised. Shortcut for ``config_id.config_type``.

        :rtype: Configuration item type.
        :rtype: dockermap.map.input.ItemType
        """
        return self._config_id.config_type

    @property
    def action_type(self):
        """
        Action type on which the error occurred.

        :return: Action type.
        :rtype: dockermap.map.action.ActionEnum
        """
        return self._action_type


@six.python_2_unicode_compatible
class ActionException(SourceExceptionMixin, ClientExceptionMixin, ActionExceptionMixin, Exception):
    """
    Exception type for issues that occur while running a single action for a configuration.
    """
    def __str__(self):
        return "Error during invocation of action {0._action_type} on {0._config_id}: {0.source_message}".format(self)


@six.python_2_unicode_compatible
class ActionRunnerException(SourceExceptionMixin, ClientExceptionMixin, ActionExceptionMixin, PartialResultsMixin,
                            Exception):
    """
    Errors that occur while running a set of actions, while some of them might already be completed.
    """
    @classmethod
    def from_action_exception(cls, ae, partial_results, *args, **kwargs):
        return cls(ae.source_exception, ae.client_name, ae.config_id, ae.action_type, partial_results, *args, **kwargs)

    def __str__(self):
        return "Error while running action {0._action_type} on {0._config_id}: {0.source_message}".format(self)


@six.python_2_unicode_compatible
class MapIntegrityError(Exception):
    """
    Exception for cases where the configurations are not consistent (e.g. a volume alias is missing on the map).
    """
    def __init__(self, message):
        self._message = message

    @property
    def message(self):
        return self._message

    def __str__(self):
        return self._message


class ScriptRunException(Exception):
    pass


class ScriptActionException(Exception):
    pass
