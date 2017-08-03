# -*- coding: utf-8 -*-
from collections import namedtuple

import six

from ...utils import merge_list
from ..input import NotSet, get_list


_IMMUTABLE_TYPES = (type(None), type(NotSet), bool, float, tuple, frozenset) + six.integer_types + six.string_types


class ConfigurationProperty(namedtuple('ConfigurationProperty', ['attr_type', 'default', 'input_func',
                                                                 'merge_func', 'update'])):
    def __new__(cls, attr_type=None, default=NotSet, input_func=None, merge_func=None, update=True):
        if attr_type not in _IMMUTABLE_TYPES and default is NotSet:
            default = attr_type
        if attr_type is list:
            if input_func is None:
                input_func = get_list
            if merge_func is None:
                merge_func = merge_list
        return super(ConfigurationProperty, cls).__new__(cls, attr_type=attr_type, default=default,
                                                         input_func=input_func, merge_func=merge_func,
                                                         update=update)

CP = ConfigurationProperty


def _get_property(prop_name, config_property, doc=None):
    default, input_func = config_property[1:3]

    if callable(default):
        def get_item(self):
            return self._config.setdefault(prop_name, default())
    else:
        def get_item(self):
            return self._config.get(prop_name, default)

    if input_func:
        def set_item(self, value):
            self._config[prop_name] = input_func(value)
    else:
        def set_item(self, value):
            self._config[prop_name] = value

    def del_item(self):
        del self._config[prop_name]

    return property(get_item, set_item, del_item, doc)


class ConfigurationMeta(type):
    def __new__(mcs, name, bases, dct):
        new_cls = super(ConfigurationMeta, mcs).__new__(mcs, name, bases, dct)
        new_cls.CONFIG_PROPERTIES = attrs = {attr_name: config
                                             for attr_name, config in six.iteritems(dct)
                                             if isinstance(config, ConfigurationProperty)}
        docstrings = new_cls.DOCSTRINGS
        for attr_name, config in six.iteritems(attrs):
            doc = docstrings.get(attr_name)
            setattr(new_cls, attr_name, _get_property(attr_name, config, doc=doc))
        return new_cls


class ConfigurationObject(six.with_metaclass(ConfigurationMeta)):
    DOCSTRINGS = {}

    def __init__(self, values=None, **kwargs):
        self._config = {}
        if values:
            self.update(values, copy_instance=True)
        if kwargs:
            self.update_from_dict(kwargs)

    def __repr__(self):
        props = ', '.join('{0}={1!r}'.format(key, value)
                          for key, value in six.iteritems(self._config))
        return '<{0}({1})>'.format(self.__class__.__name__, props)

    def update_default_from_dict(self, key, value):
        pass

    def merge_default_from_dict(self, key, value, lists_only=False):
        pass

    def _merge_value(self, attr_type, merge_func, key, value):
        get_current = self._config.get
        if attr_type is list:
            if value and merge_func:
                current = get_current(key)
                if current:
                    merge_func(current, value)
                else:
                    self._config[key] = value[:]
        elif attr_type is dict:
            if value:
                current = get_current(key)
                if merge_func and current:
                    merge_func(current, value)
                elif current:
                    current.update(value)
                else:
                    self._config[key] = value.copy()
        elif merge_func and value:
            self._config[key] = merge_func(get_current(key), value)
        else:
            self._config[key] = value

    def update_from_dict(self, dct):
        if not dct:
            return
        all_props = self.__class__.CONFIG_PROPERTIES
        for key, value in six.iteritems(dct):
            attr_config = all_props.get(key)
            if attr_config:
                if attr_config.update:
                    setattr(self, key, value)
            else:
                self.update_default_from_dict(key, value)

    def update_from_obj(self, obj, copy=False):
        obj_config = obj._config
        update_props = {name: config
                        for name, config in six.iteritems(self.__class__.CONFIG_PROPERTIES)
                        if config.update}
        if copy:
            for key, value in six.iteritems(obj_config):
                attr_config = update_props.get(key)
                if attr_config:
                    attr_type = attr_config.attr_type
                    if attr_type is list:
                        self._config[key] = value[:]
                    elif attr_type is dict:
                        self._config[key] = value.copy()
                    else:
                        self._config[key] = value
        else:
            self._config.update({key: value
                                 for key, value in six.iteritems(obj_config)
                                 if key in update_props})

    def merge_from_dict(self, dct, lists_only=False):
        if not dct:
            return
        all_props = self.__class__.CONFIG_PROPERTIES
        for key, value in six.iteritems(dct):
            attr_config = all_props.get(key)
            if attr_config:
                attr_type, default, input_func, merge_func = attr_config[:4]
                if merge_func is not False and value != default and (not lists_only or attr_type is list):
                    if input_func:
                        value = input_func(value)
                    self._merge_value(attr_type, merge_func, key, value)
            else:
                self.merge_default_from_dict(key, value, lists_only=lists_only)

    def merge_from_obj(self, obj, lists_only=False):
        obj_config = obj._config
        all_props = self.__class__.CONFIG_PROPERTIES
        for key, value in six.iteritems(obj_config):
            attr_config = all_props[key]
            attr_type, default, __, merge_func = attr_config[:4]
            if merge_func is not False and value != default and (not lists_only or attr_type is list):
                self._merge_value(attr_type, merge_func, key, value)

    def update(self, values, copy_instance=False):
        """
        Updates the configuration with the contents of the given configuration object or dictionary. In case
        of a dictionary, only valid attributes for this class are considered. Existing attributes are replaced with
        the new values.

        :param values: Dictionary or ConfigurationObject to update this configuration with.
        :type values: dict | ConfigurationObject
        :param copy_instance: Copies lists and dictionaries. Only has an effect if ``values`` is a ConfigurationObject.
        :type copy_instance: bool
        :return:
        """
        if isinstance(values, self.__class__):
            self.update_from_obj(values, copy=copy_instance)
        elif isinstance(values, dict):
            self.update_from_dict(values)
        else:
            raise ValueError("{0} or dictionary expected; found '{1}'.".format(self.__class__.__name__,
                                                                               type(values).__name__))

    def merge(self, values, lists_only=False):
        """
        Merges list-based attributes into one list including unique elements from both lists. When ``lists_only`` is
        set to ``False``, updates dictionaries and overwrites single-value attributes.

        :param values: Values to update the ConfigurationObject with.
        :type values: dict | ConfigurationObject
        :param lists_only: Ignore single-value attributes and update dictionary options.
        :type lists_only: bool
        """
        if isinstance(values, self.__class__):
            self.merge_from_obj(values, lists_only=lists_only)
        elif isinstance(values, dict):
            self.merge_from_dict(values, lists_only=lists_only)
        else:
            raise ValueError("{0} or dictionary expected; found '{1}'.".format(self.__class__.__name__,
                                                                               type(values).__name__))

    def copy(self):
        return self.__class__(self)
