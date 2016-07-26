# -*- coding: utf-8 -*-
import six


def _update_instance(instance, obj_dict):
    if not obj_dict:
        return
    for p_name in instance.__class__.core_properties:
        if p_name in obj_dict:
            object.__setattr__(instance, p_name, obj_dict.pop(p_name))


class PropertyDictMeta(type):
    def __init__(cls, name, bases, dct):
        cls.core_properties = cp = [d_name for d_name, d_type in six.iteritems(dct) if isinstance(d_type, property)]
        cp.extend('_{0}'.format(d_name) for d_name in cp[:])
        cp_set = set(cp)
        cp_add = cp_set.add
        for base in bases:
            if hasattr(base, 'core_properties'):
                cp.extend(b_cp for b_cp in base.core_properties if b_cp not in cp_set and not cp_add(b_cp))
        super(PropertyDictMeta, cls).__init__(name, bases, dct)


class DictMap(six.with_metaclass(PropertyDictMeta, dict)):
    """
    Utility class which allows access to a dictionary by attributes and keys. Also overrides the default iteration to
    return keys and values.
    """
    def __init__(self, *args, **kwargs):
        _update_instance(self, kwargs)
        super(DictMap, self).__init__(*args, **kwargs)

    def __getattr__(self, item):
        return self[item]

    def __setattr__(self, key, value):
        if key in self.__class__.core_properties:
            object.__setattr__(self, key, value)
        else:
            self[key] = value

    def __delattr__(self, item):
        if hasattr(self, item):
            super(DictMap, self).__delattr__(item)
        else:
            self.pop(item)

    def __iter__(self):
        return six.iteritems(self)

    def update(self, other=None, **kwargs):
        if other is not None:
            if isinstance(other, self.__class__):
                for p in self.__class__.core_properties:
                    object.__setattr__(self, p, getattr(other, p))
            elif isinstance(other, dict):
                other = other.copy()
                _update_instance(self, other)
            else:
                raise ValueError("Expected {0} or dictionary; found '{1}'".format(type(self).__name__, type(other).__name__))
        _update_instance(self, kwargs)
        super(DictMap, self).update(other, **kwargs)
