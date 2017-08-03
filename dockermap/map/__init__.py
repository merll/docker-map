# -*- coding: utf-8 -*-
from collections import defaultdict
import itertools
import six
from enum import Enum

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

    def __repr__(self):
        default_repr = super(AttributeMixin, self).__repr__()
        cls = self.__class__
        props = ', '.join('{0}={1!r}'.format(p_name, getattr(self, p_name))
                          for p_name in cls.external_properties)
        return '<{0}({1}): {2}>'.format(cls.__name__, props, default_repr)

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
        return len(self) > 0 or any(getattr(self, p) for p in self.__class__.internal_properties)

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


class FlagsMeta(type):
    def __new__(mcs, name, bases, dct):
        fields = {}
        for base in bases:
            if hasattr(base, 'fields'):
                fields.update(base.fields)
        fields.update((field_name, field_value)
                      for field_name, field_value in six.iteritems(dct)
                      if isinstance(field_value, int))
        dct['fields'] = fields
        new_cls = type.__new__(mcs, name, bases, dct)
        for field_name, field_value in six.iteritems(fields):
            setattr(new_cls, field_name, new_cls(field_value))

        def _get_fields(self):
            set_fields = [field_name
                          for field_name, field_value in six.iteritems(fields)
                          if self & field_value]
            return '{0}({1})'.format(name, ', '.join(set_fields))
        new_cls.__repr__ = _get_fields

        return new_cls


class Flags(six.with_metaclass(FlagsMeta, int)):
    NONE = 0

    def __contains__(self, other):
        return self & other > 0

    def __or__(self, other):
        return self.__class__(int.__or__(self, other))

    __add__ = __or__

    def __xor__(self, other):
        return self.__class__(int.__xor__(self, other))

    __sub__ = __xor__


class SimpleEnum(Enum):
    # Just like regular enum, but less verbose.
    def __repr__(self):
        return '{0.__class__.__name__}.{0.name}'.format(self)
