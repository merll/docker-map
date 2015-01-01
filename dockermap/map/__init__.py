# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six


class DictMap(dict):
    """
    Utility class which allows access to a dictionary by attributes and keys. Also overrides the default iteration to
    return keys and values.
    """
    def __getattr__(self, item):
        return self[item]

    def __setattr__(self, key, value):
        if hasattr(self, key):
            super(DictMap, self).__setattr__(key, value)
        else:
            self[key] = value

    def __iter__(self):
        return six.iteritems(self)
