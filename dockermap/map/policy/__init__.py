# -*- coding: utf-8 -*-
from __future__ import unicode_literals


CONFIG_FLAG_ATTACHED = 1               # Container is an attached volume.
CONFIG_FLAG_DEPENDENT = 1 << 1         # Container is checked in a relation to a dependent / dependency container.
CONFIG_FLAG_PERSISTENT = 1 << 2        # Container is persistent.


class PolicyUtil(object):
    """
    Base class for utility objects used by a policy and referring back to it.

    :param policy: Policy object instance.
    :type policy: BasePolicy
    """
    def __init__(self, policy):
        self._policy = policy


class ForwardGeneratorMixin(object):
    """
    Defines the dependency path as dependencies of a container configuration.
    """
    def get_dependency_path(self, map_name, config_name):
        return self._policy.get_dependencies(map_name, config_name)


class ReverseGeneratorMixin(object):
    """
    Defines the dependency path as dependents of a container configuration.
    """
    def get_dependency_path(self, map_name, config_name):
        return self._policy.get_dependents(map_name, config_name)
