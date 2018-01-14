# -*- coding: utf-8 -*-
from collections import namedtuple, OrderedDict

import six

from ...utils import merge_list
from ..input import NotSet, NamedTupleList, get_list


_IMMUTABLE_TYPES = (bool, float, tuple, frozenset) + six.integer_types + six.string_types


class ConfigurationProperty(namedtuple('ConfigurationProperty', ['attr_type', 'default', 'input_func',
                                                                 'merge_func'])):
    _field_order = 0

    def __new__(cls, attr_type=None, default=NotSet, input_func=None, merge_func=None):
        if attr_type:
            if attr_type not in _IMMUTABLE_TYPES and default is NotSet:
                default = attr_type
            if attr_type and issubclass(attr_type, list):
                if input_func is None:
                    if issubclass(attr_type, NamedTupleList):
                        input_func = attr_type
                    else:
                        input_func = get_list
                if merge_func is None:
                    merge_func = merge_list

        new_instance = super(ConfigurationProperty, cls).__new__(cls, attr_type=attr_type, default=default,
                                                                 input_func=input_func, merge_func=merge_func)
        new_instance._field_order = cls._field_order
        cls._field_order += 1
        return new_instance


CP = ConfigurationProperty


def _get_property(prop_name, doc=None):
    def get_item(self):
        return self._config[prop_name]

    def set_item(self, value):
        self._modified.add(prop_name)
        self._config[prop_name] = value

    return property(get_item, set_item, doc=doc)


class ConfigurationMeta(type):
    def __new__(mcs, name, bases, dct):
        new_cls = super(ConfigurationMeta, mcs).__new__(mcs, name, bases, dct)
        attrs = sorted([(attr_name, config)
                       for attr_name, config in six.iteritems(dct)
                       if isinstance(config, ConfigurationProperty)],
                       key=lambda i: i[1]._field_order)
        new_cls.CONFIG_PROPERTIES = OrderedDict(attrs)
        docstrings = new_cls.DOCSTRINGS
        for attr_name, config in attrs:
            doc = docstrings.get(attr_name)
            setattr(new_cls, attr_name, _get_property(attr_name, doc))
        return new_cls


class ConfigurationObject(six.with_metaclass(ConfigurationMeta)):
    DOCSTRINGS = {}

    def __init__(self, values=None, **kwargs):
        all_props = self.__class__.CONFIG_PROPERTIES
        self._config = {
            attr_name: attr_config.default() if callable(attr_config.default) else attr_config.default
            for attr_name, attr_config in six.iteritems(all_props)
        }
        self._modified = set()
        if values:
            self.update(values, copy_instance=True)
        if kwargs:
            self.update_from_dict(kwargs)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self._config == other._config

    def __repr__(self):
        if not self._modified:
            status = ''
        else:
            status = '(Modified) '
        props = ', '.join('{0}={1!r}'.format(key, value)
                          for key, value in six.iteritems(self._config))
        return '<{0}({1}{2})>'.format(self.__class__.__name__, status, props)

    def update_default_from_dict(self, key, value):
        """
        When updating from a dictionary, this is processed for any key that does not match a ``ConfigurationProperty``.

        :param key: Dictionary key.
        :type key: unicode | str
        :param value: Dictionary value.
        """
        pass

    def merge_default_from_dict(self, key, value, lists_only=False):
        """
        When merging from a dictionary, this is processed for any key that does not match a ``ConfigurationProperty``.

        :param key: Dictionary key.
        :type key: unicode | str
        :param value: Dictionary value.
        :param lists_only: Matches the ``list_only`` argument from :meth:`ConfigurationObject.merge_from_dict`.
        :type lists_only: bool
        :return:
        """
        pass

    def _merge_value(self, attr_type, merge_func, key, value):
        get_current = self._config.get
        if attr_type:
            if issubclass(attr_type, list):
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
        """
        Updates this configuration object from a dictionary.

        See :meth:`ConfigurationObject.update` for details.

        :param dct: Values to update the ConfigurationObject with.
        :type dct: dict
        """
        if not dct:
            return
        all_props = self.__class__.CONFIG_PROPERTIES
        for key, value in six.iteritems(dct):
            attr_config = all_props.get(key)
            if attr_config:
                setattr(self, key, value)
            else:
                self.update_default_from_dict(key, value)

    def update_from_obj(self, obj, copy=False):
        """
        Updates this configuration object from another.

        See :meth:`ConfigurationObject.update` for details.

        :param obj: Values to update the ConfigurationObject with.
        :type obj: ConfigurationObject
        :param copy: Copies lists and dictionaries.
        :type copy: bool
        """
        obj.clean()
        obj_config = obj._config
        all_props = self.__class__.CONFIG_PROPERTIES
        if copy:
            for key, value in six.iteritems(obj_config):
                attr_config = all_props.get(key)
                if attr_config:
                    attr_type = attr_config.attr_type
                    if attr_type:
                        if issubclass(attr_type, list):
                            self._config[key] = value[:]
                        elif attr_type is dict:
                            self._config[key] = value.copy()
                    else:
                        self._config[key] = value
                    self._modified.discard(key)
        else:
            filtered_dict = {key: value
                             for key, value in six.iteritems(obj_config)
                             if key in all_props}
            self._config.update(filtered_dict)
            self._modified.difference_update(filtered_dict.keys())

    def merge_from_dict(self, dct, lists_only=False):
        """
        Merges a dictionary into this configuration object.

        See :meth:`ConfigurationObject.merge` for details.

        :param dct: Values to update the ConfigurationObject with.
        :type dct: dict
        :param lists_only: Ignore single-value attributes and update dictionary options.
        :type lists_only: bool
        """
        if not dct:
            return
        self.clean()
        all_props = self.__class__.CONFIG_PROPERTIES
        for key, value in six.iteritems(dct):
            attr_config = all_props.get(key)
            if attr_config:
                attr_type, default, input_func, merge_func = attr_config[:4]
                if (merge_func is not False and value != default and
                        (not lists_only or (attr_type and issubclass(attr_type, list)))):
                    if input_func:
                        value = input_func(value)
                    self._merge_value(attr_type, merge_func, key, value)
            else:
                self.merge_default_from_dict(key, value, lists_only=lists_only)

    def merge_from_obj(self, obj, lists_only=False):
        """
        Merges a configuration object into this one.

        See :meth:`ConfigurationObject.merge` for details.

        :param obj: Values to update the ConfigurationObject with.
        :type obj: ConfigurationObject
        :param lists_only: Ignore single-value attributes and update dictionary options.
        :type lists_only: bool
        """
        self.clean()
        obj.clean()
        obj_config = obj._config
        all_props = self.__class__.CONFIG_PROPERTIES
        for key, value in six.iteritems(obj_config):
            attr_config = all_props[key]
            attr_type, default, __, merge_func = attr_config[:4]
            if (merge_func is not False and value != default and
                    (not lists_only or (attr_type and issubclass(attr_type, list)))):
                self._merge_value(attr_type, merge_func, key, value)

    def update(self, values, copy_instance=False):
        """
        Updates the configuration with the contents of the given configuration object or dictionary.

        In case of a dictionary, only valid attributes for this class are considered. Existing attributes are replaced
        with the new values. The object is not cleaned before or after, i.e. may accept invalid input.

        In case of an update by object, that object is cleaned before the update, so that updated values should be
        validated. However, already-stored values are not cleaned before or after.

        :param values: Dictionary or ConfigurationObject to update this configuration with.
        :type values: dict | ConfigurationObject
        :param copy_instance: Copies lists and dictionaries. Only has an effect if ``values`` is a ConfigurationObject.
        :type copy_instance: bool
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
        set to ``False``, updates dictionaries and overwrites single-value attributes. The resulting configuration
        is 'clean', i.e. input values converted and validated. If the conversion is not possible, a ``ValueError`` is
        raised.

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
        """
        Creates a copy of the current instance.

        :return: Copy of this ``ConfigurationObject``.
        :rtype: ConfigurationObject
        """
        return self.__class__(self)

    def clean(self):
        """
        Cleans the input values of this configuration object.

        Fields that have gotten updated through properties are converted to configuration values that match the
        format needed by functions using them. For example, for list-like values it means that input of single strings
        is transformed into a single-entry list. If this conversion fails, a ``ValueError`` is raised.
        """
        all_props = self.__class__.CONFIG_PROPERTIES
        for prop_name in self._modified:
            attr_config = all_props.get(prop_name)
            if attr_config and attr_config.input_func:
                self._config[prop_name] = attr_config.input_func(self._config[prop_name])
        self._modified.clear()

    @property
    def is_clean(self):
        """
        Whether the current object is 'clean', i.e. has no non-converted input.

        :return: ``True`` if no values have been modified since the last ``clean``, ``False`` otherwise.
        :rtype: bool
        """
        return not self._modified

    def as_dict(self):
        """
        Returns a copy of the configuration dictionary. Changes in this should not reflect on the original
        object.

        :return: Configuration dictionary.
        :rtype: dict
        """
        self.clean()
        d = OrderedDict()
        all_props = self.__class__.CONFIG_PROPERTIES
        for attr_name, attr_config in six.iteritems(all_props):
            value = self._config[attr_name]
            attr_type = attr_config.attr_type
            if attr_type:
                if value:
                    if issubclass(attr_type, list):
                        if issubclass(attr_type, NamedTupleList):
                            d[attr_name] = [i._asdict() for i in value]
                        else:
                            d[attr_name] = value[:]
                    elif attr_type is dict:
                        d[attr_name] = dict(value)
            elif value is not NotSet:
                d[attr_name] = value
        return d
