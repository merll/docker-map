# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from six import string_types, iteritems

from ...functional import uses_type_registry, lazy_type
from .. import DefaultDictMap
from . import ConfigurationObject, CP


class VolumeConfiguration(ConfigurationObject):
    """
    Configuration class for networks.
    """
    default_path = CP()
    driver = CP(default='local')
    driver_options = CP(dict)
    create_options = CP(dict)

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and (isinstance(args[0], string_types + (lazy_type, )) or uses_type_registry(args[0])):
            super(VolumeConfiguration, self).__init__(default_path=args[0])
        else:
            super(VolumeConfiguration, self).__init__(*args, **kwargs)

    def update_from_dict(self, dct):
        if isinstance(dct, string_types + (lazy_type, )) or uses_type_registry(dct):
            self.default_path = dct
            self.driver = 'local'
            self.driver_options = {}
            self.create_options = {}
        else:
            super(VolumeConfiguration, self).update_from_dict(dct)

    def merge_from_dict(self, dct, lists_only=False):
        if not lists_only and isinstance(dct, string_types + (lazy_type, )) or uses_type_registry(dct):
            self.default_path = dct
        else:
            super(VolumeConfiguration, self).merge_from_dict(dct, lists_only=lists_only)

    DOCSTRINGS = {
        'default_path': "Default path of the volume when used in a container.",
        'driver': "The volume driver name.",
        'driver_options': "Custom options to the driver.",
        'create_options': "Additional keyword arguments to creating the volume.",
    }


class VolumeConfigurationMap(DefaultDictMap):
    default_factory = VolumeConfiguration

    def __init__(self, default_factory=None, *args, **kwargs):
        super(DefaultDictMap, self).__init__(default_factory or self.__class__.default_factory,
                                             *args, **kwargs)

    def __setitem__(self, key, value):
        if isinstance(value, string_types + (lazy_type, )) or uses_type_registry(value):
            value = self.default_factory(default_path=value)
        super(VolumeConfigurationMap, self).__setitem__(key, value)

    @property
    def default_paths(self):
        return {key: value.default_path for key, value in self}

    def update(self, other=None, **kwargs):
        set_item = super(VolumeConfigurationMap, self).__setitem__
        if isinstance(other, dict) and not isinstance(other, self.__class__):
            for key, value in iteritems(other):
                if isinstance(value, string_types + (lazy_type,)) or uses_type_registry(value):
                    value = self.default_factory(default_path=value)
                set_item(key, value)
        else:
            super(VolumeConfigurationMap, self).update(other)
        for key, value in iteritems(kwargs):
            if isinstance(value, string_types + (lazy_type,)) or uses_type_registry(value):
                value = self.default_factory(default_path=value)
            set_item(key, value)
