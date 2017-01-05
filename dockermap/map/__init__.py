# -*- coding: utf-8 -*-
from collections import defaultdict
import itertools
import six

from ..utils import merge_list


def _update_instance_from_dict(instance, obj_dict):
    if not obj_dict:
        return
    for p_name in instance.__class__.external_properties:
        if p_name in obj_dict:
            object.__setattr__(instance, p_name, obj_dict.pop(p_name))


def _update_instance_from_obj(instance, obj):
    for p_name in instance.__class__.internal_properties:
        object.__setattr__(instance, p_name, getattr(obj, p_name))


class PropertyDictMeta(type):
    def __init__(cls, name, bases, dct):
        cls.core_properties = cp = [d_name for d_name, d_type in six.iteritems(dct) if isinstance(d_type, property)]
        cls.external_properties = ce = cp[:]
        cls.internal_properties = ci = ['_{0}'.format(d_name) for d_name in cp]
        cp.extend(ci)
        cp_bases = [base for base in bases if hasattr(base, 'core_properties')]
        merge_list(cp, itertools.chain.from_iterable(base.core_properties for base in cp_bases))
        merge_list(ce, itertools.chain.from_iterable(base.external_properties for base in cp_bases))
        merge_list(ci, itertools.chain.from_iterable(base.internal_properties for base in cp_bases))
        cls.core_property_set = set(cp)
        super(PropertyDictMeta, cls).__init__(name, bases, dct)


class AttributeMixin(six.with_metaclass(PropertyDictMeta)):
    """
    Utility class which allows access to a dictionary by attributes and keys. Also overrides the default iteration to
    return keys and values.
    """
    def __init__(self, *args, **kwargs):
        _update_instance_from_dict(self, kwargs)
        super(AttributeMixin, self).__init__(*args, **kwargs)

    def __getattr__(self, item):
        return self[item]

    def __setattr__(self, key, value):
        if key in self.__class__.core_property_set:
            object.__setattr__(self, key, value)
        else:
            self[key] = value

    def __delattr__(self, item):
        if hasattr(self, item):
            object.__delattr__(self, item)
        else:
            self.pop(item)

    def __iter__(self):
        return six.iteritems(self)

    def __nonzero__(self):
        return len(self) > 0 and any(getattr(self, p) for p in self.__class__.internal_properties)

    __bool__ = __nonzero__

    def __eq__(self, other):
        return super(AttributeMixin, self).__eq__(other) and all(getattr(self, p) == getattr(other, p)
                                                                 for p in self.__class__.internal_properties)

    def update(self, other=None, **kwargs):
        if other is not None:
            if isinstance(other, self.__class__):
                _update_instance_from_obj(self, other)
            elif isinstance(other, dict):
                other = other.copy()
                _update_instance_from_dict(self, other)
            else:
                raise TypeError("Expected {0} or dictionary; found '{1}'".format(type(self).__name__, type(other).__name__))
        _update_instance_from_dict(self, kwargs)
        super(AttributeMixin, self).update(other, **kwargs)


class DictMap(AttributeMixin, dict):
    def copy(self):
        new_instance = self.__class__(self)
        _update_instance_from_obj(new_instance, self)
        return new_instance


class DefaultDictMap(AttributeMixin, defaultdict):
    def copy(self):
        new_instance = self.__class__(self.default_factory, self)
        _update_instance_from_obj(new_instance, self)
        return new_instance
