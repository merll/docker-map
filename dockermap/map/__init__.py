# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six


class DictMap(object):
    """
    Utility class which allows access to a dictionary by attributes and keys.
    """
    def __init__(self):
        self._map = {}

    def __getitem__(self, item):
        return self.get(item)

    def __getattr__(self, item):
        return self.get(item)

    def __iter__(self):
        return six.iteritems(self._map)

    def keys(self):
        """
        Returns the keys of the underlying dictionary.

        :return: Dictionary keys.
        :rtype: list
        """
        return self._map.keys()

    def get(self, item):
        """
        Returns the value associated with the key `item`.

        :param item: Dictionary key.
        :type item: unicode
        :return: Value associated with this key.
        :rtype: any
        """
        return self._map[item]

    def update(self, other=None, **kwargs):
        """
        Updates the underlying dictionary. Same as :func:`dict.update`.

        :type other: dict
        :param kwargs: dict
        """
        self._map.update(other, **kwargs)
