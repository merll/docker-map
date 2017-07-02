# -*- coding: utf-8 -*-
from abc import ABCMeta

from six import with_metaclass

CONFIG_FLAG_DEPENDENT = 1  # Configuration is checked in a relation to a dependent / dependency container.
CONTAINER_CONFIG_FLAG_ATTACHED = 1 << 1          # Container is an attached volume.
CONTAINER_CONFIG_FLAG_PERSISTENT = 1 << 2        # Container is persistent.


class PolicyUtilMeta(type):
    def __init__(cls, name, bases, dct):
        cls.policy_options = options = []
        for base in bases:
            if hasattr(base, 'policy_options'):
                options.extend(base.policy_options)
        opts = dct.get('policy_options')
        if opts:
            options.extend(opts)
        super(PolicyUtilMeta, cls).__init__(name, bases, dct)


class ABCPolicyUtilMeta(ABCMeta, PolicyUtilMeta):
    pass


class PolicyUtil(with_metaclass(PolicyUtilMeta)):
    """
    Base class for utility objects used by a policy and referring back to it.

    :param policy: Policy object instance.
    :type policy: BasePolicy
    """
    policy_options = []

    def __init__(self, policy, kwargs):
        for option_name in self.__class__.policy_options:
            if option_name in kwargs:
                setattr(self, option_name, kwargs.pop(option_name))
        self._policy = policy

    def get_options(self):
        return {
            option_name: getattr(self, option_name)
            for option_name in self.__class__.policy_options
        }
