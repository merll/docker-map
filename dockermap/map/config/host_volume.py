# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import posixpath

from ...functional import resolve_value
from .. import DictMap
from ..input import NotSet


def get_host_path(root, path, instance=None):
    """
    Generates the host path for a container volume. If the given path is a dictionary, uses the entry of the instance
    name.

    :param root: Root path to prepend, if ``path`` does not already describe an absolute path.
    :type root: unicode | str | AbstractLazyObject
    :param path: Path string or dictionary of per-instance paths.
    :type path: unicode | str | dict | AbstractLazyObject
    :param instance: Optional instance name.
    :type instance: unicode | str
    :return: Path on the host that is mapped to the container volume.
    :rtype: unicode | str
    """
    r_val = resolve_value(path)
    if isinstance(r_val, dict):
        r_instance = instance or 'default'
        r_path = resolve_value(r_val.get(r_instance))
        if not r_path:
            raise ValueError("No path defined for instance {0}.".format(r_instance))
    else:
        r_path = r_val
    r_root = resolve_value(root)
    if r_path and r_root and (r_path[0] != posixpath.sep):
        return posixpath.join(r_root, r_path)
    return r_path


class HostVolumeConfiguration(DictMap):
    """
    Class for storing volumes, as shared from the host with Docker containers.

    :param root: Optional root directory for host volumes.
    :type root: unicode | str
    """
    def __init__(self, *args, **kwargs):
        self._root = NotSet
        super(HostVolumeConfiguration, self).__init__(*args, **kwargs)

    @property
    def root(self):
        """
        Root directory for host volumes; if set, relative paths of host-shared directories will be prefixed with
        this.

        :return: Root directory for host volumes.
        :rtype: unicode | str
        """
        return self._root

    @root.setter
    def root(self, value):
        self._root = value

    def get_path(self, item, instance=None):
        return get_host_path(self._root, self[item], instance)
