# -*- coding: utf-8 -*-
from six import with_metaclass

from ..policy import PolicyUtilMeta, PolicyUtil


class RunnerMeta(PolicyUtilMeta):
    def __init__(cls, name, bases, dct):
        cls._a_methods = attached_methods = []
        cls._i_methods = instance_methods = []
        for base in bases:
            if hasattr(base, 'attached_action_method_names'):
                attached_methods.extend((a_type_name, a_method_name)
                                        for a_type_name, a_method_name in base.attached_action_method_names)
            if hasattr(base, 'instance_action_method_names'):
                instance_methods.extend((a_type_name, a_method_name)
                                        for a_type_name, a_method_name in base.instance_action_method_names)
        a_method_names = dct.get('attached_action_method_names')
        if a_method_names:
            attached_methods.extend((a_type_name, a_method_name)
                                    for a_type_name, a_method_name in a_method_names)
        i_method_names = dct.get('instance_action_method_names')
        if i_method_names:
            instance_methods.extend((a_type_name, a_method_name)
                                    for a_type_name, a_method_name in i_method_names)
        super(RunnerMeta, cls).__init__(name, bases, dct)


class AbstractRunner(with_metaclass(RunnerMeta, PolicyUtil)):
    def __new__(cls, *args, **kwargs):
        instance = super(AbstractRunner, cls).__new__(cls, *args, **kwargs)
        instance.attached_methods = {
            action_name: getattr(instance, action_method)
            for action_name, action_method in cls._a_methods
        }
        instance.instance_methods = {
            action_name: getattr(instance, action_method)
            for action_name, action_method in cls._i_methods
        }
        return instance
