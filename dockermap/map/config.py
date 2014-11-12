# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import posixpath
from collections import namedtuple
import operator
import six

from . import DictMap


LIST_ATTRIBUTES = 'instances', 'shares', 'uses', 'attaches'

HostShare = namedtuple('HostShare', ('volume', 'readonly'))
ContainerLink = namedtuple('ContainerLink', ('container', 'alias'))


def _get_list(value):
    if value is None:
        return []
    elif isinstance(value, (list, tuple)):
        return list(value)
    elif isinstance(value, six.string_types):
        return [value]
    raise ValueError("Invalid type; expected a list, tuple, or string type, found {0}.".format(type(value)))


def _get_listed_tuples(value, element_type, conversion_func):
    if value is None:
        return []
    elif isinstance(value, element_type):
        return [value]
    elif isinstance(value, six.string_types):
        return [conversion_func(value)]
    elif isinstance(value, (list, tuple)):
        return [conversion_func(e) for e in value]
    elif isinstance(value, dict):
        return [conversion_func(e) for e in six.iteritems(value)]
    raise ValueError("Invalid type; expected {0}, list, tuple, or dict; found {1}.".format(element_type.__name__, type(value)))


def _get_host_share(value):
    if isinstance(value, six.string_types):
        return HostShare(value, False)
    elif isinstance(value, (list, tuple)):
        if len(value) == 2:
            return HostShare(value[0], bool(value[1]))
        raise ValueError("Invalid element length; only tuples and lists of length 2 can be converted to a HostShare tuple.")
    elif isinstance(value, dict):
        if len(value) == 1:
            k, v = value.items()[0]
            return HostShare(k, bool(v))
        raise ValueError("Invalid element length; only dicts with one element can be converted to a HostShare tuple.")
    raise ValueError("Invalid type; expected a list, tuple, or string type, found {0}.".format(type(value)))


def _get_container_link(value):
    if isinstance(value, six.string_types):
        return ContainerLink(value, value)
    elif isinstance(value, (list, tuple)):
        if len(value) == 2:
            return ContainerLink(*value)
        raise ValueError("Invalid element length; only tuples and lists of length 2 can be converted to a ContainerLink tuple.")
    raise ValueError("Invalid type; expected a list, tuple, or string type, found {0}.".format(type(value)))


_get_host_shares = lambda value: _get_listed_tuples(value, HostShare, _get_host_share)
_get_container_links = lambda value: _get_listed_tuples(value, ContainerLink, _get_container_link)


class ContainerConfiguration(object):
    """
    Class to maintain resources that are associated with a container.

    :param kwargs: Optional initial values.
    """
    def __init__(self, **kwargs):
        self._image = None
        self._instances = []
        self._shares = []
        self._binds = []
        self._uses = []
        self._links_to = []
        self._attaches = []
        self._user = None
        self._permissions = None
        self._persistent = False
        self._create_kwargs = None
        self._start_kwargs = None
        self.update(kwargs)

    def __repr__(self):
        return '{0} shares: {1}; binds: {2}; uses: {3}; attaches: {4}'.format(self.__class__.__name__,
                                                                              self._shares, self._binds, self._uses,
                                                                              self._attaches)

    @property
    def image(self):
        """
        The base image of the container. If set to `None`, the containers will be instantiated with an image that
        has the same name.

        :return: Base image name.
        :rtype: unicode
        """
        return self._image

    @image.setter
    def image(self, value):
        self._image = value

    @property
    def instances(self):
        """
        Separate instances of a container, if any. By default there is one instance of each container. If set,
        containers will be created for each instance in the format `map_name.container_name.instance`.

        :return: Instance names.
        :rtype: list
        """
        return self._instances

    @instances.setter
    def instances(self, value):
        self._instances = _get_list(value)

    @property
    def shares(self):
        """
        Shared volumes for a container.

        :return: Shared volumes.
        :rtype: list
        """
        return self._shares

    @shares.setter
    def shares(self, value):
        self._shares = _get_list(value)

    @property
    def binds(self):
        """
        Returns the host volume shares for a container. These will be added to the shared volumes, and mapped to a host
        volume on container start. Each bind should be an instance of :class:`HostShare` with parameters
        `(volume_alias: unicode, readonly: bool)`.

        :return: Host volumes.
        :rtype: list
        """
        return self._binds

    @binds.setter
    def binds(self, value):
        self._binds = _get_host_shares(value)

    @property
    def uses(self):
        """
        Volumes used from other containers. This can be a combination of attached volume aliases, and container
        names if all volumes are to be used of that container.

        :return: Used volumes.
        :rtype: list
        """
        return self._uses

    @uses.setter
    def uses(self, value):
        self._uses = _get_list(value)

    @property
    def links(self):
        """
        Linked containers. Links are set in the format `ContainerLink(name, alias)`, where the name is the linked
        container's name, and the alias name the alias to use for this container instance.

        :return: Containers to be linked to when the container is started.
        :rtype: list
        """
        return self._links_to

    @links.setter
    def links(self, value):
        self._links_to = _get_container_links(value)

    @property
    def attaches(self):
        """
        Names of containers that are attached to instances of this one. If set, an empty container will be
        created with the purpose of sharing a volume. This volume is automatically shared with this one, but also
        available to other containers.

        :return: Attached containers.
        :rtype: list
        """
        return self._attaches

    @attaches.setter
    def attaches(self, value):
        self._attaches = _get_list(value)

    @property
    def user(self):
        """
        User name / group or id to launch the container with and to which the owner is set in attached
        containers. Can be set as a string (`user_name` or `user_name:group`), ids (e.g. `user_id:group_id`), tuple
        (`(user_name, group_name)`), or int (`user_id`).

        :return: User name and (optional) group.
        :rtype: unicode, tuple, or int
        """
        return self._user

    @user.setter
    def user(self, value):
        self._user = value

    @property
    def permissions(self):
        """
        Permission flags to be set for attached volumes. Can be in any notation accepted by `chmod`.

        :return: Permission flags.
        :rtype: unicode
        """
        return self._permissions

    @permissions.setter
    def permissions(self, value):
        self._permissions = value

    @property
    def persistent(self):
        """
        Whether the container should be removed during cleanup processes, when exited. Set to ``True`` to keep it.

        :return: Persistent flag.
        :rtype: bool
        """
        return self._persistent

    @persistent.setter
    def persistent(self, value):
        self._persistent = bool(value)

    @property
    def create_options(self):
        """
        Additional keyword args for :meth:`docker.client.Client.create_container`.

        :return: Kwargs for creating the container.
        :rtype: dict
        """
        return self._create_kwargs

    @create_options.setter
    def create_options(self, value):
        self._create_kwargs = value

    @property
    def start_options(self):
        """
        Additional keyword args for :meth:`docker.client.Client.start`.

        :return: Kwargs for starting the container.
        :rtype: dict
        """
        return self._start_kwargs

    @start_options.setter
    def start_options(self, value):
        self._start_kwargs = value

    def update(self, values):
        """
        Updates the container configuration with the contents of the given dictionary, if keys are valid attributes for
        this class. Existing attributes are replaced with the new values.

        :param values: Dictionary to update this container configuration with.
        :type values: dict
        """
        for key, value in six.iteritems(values):
            if hasattr(self, key):
                self.__setattr__(key, value)

    def merge(self, values):
        """
        Merges list-based attributes (instances, shares, uses, attaches, volumes, and binds) into one list including
        unique elements from both lists. Ignores all other attributes.

        :param values: Values to update the ContainerConfiguration with.
        :type values: ContainerConfiguration or dict
        """
        def _merge_list(attr, update_list):
            current = self.__getattribute__(attr)
            current.extend(set(update_list) - set(current))

        def _merge_first(current, update_list):
            new_keys = set(map(operator.itemgetter(0), update_list)) - set(map(operator.itemgetter(0), current))
            current.extend(filter(lambda u: u[0] in new_keys, update_list))

        if isinstance(values, dict):
            for key in LIST_ATTRIBUTES:
                value = values.get(key)
                if value:
                    _merge_list(key, value)

            _merge_first(self._binds, _get_host_shares(values.get('binds')))
            _merge_first(self._links_to, _get_container_links(values.get('links')))
        elif isinstance(values, ContainerConfiguration):
            for key in LIST_ATTRIBUTES:
                value = values.__getattribute__(key)
                if value:
                    _merge_list(key, value)

            _merge_first(self._binds, values._binds)
            _merge_first(self._links_to, values._links_to)

        else:
            raise ValueError("ContainerConfiguration or dictionary expected; found '{0}'.".format(type(values)))


class HostVolumeConfiguration(DictMap):
    """
    Class for storing volumes, as shared from the host with Docker containers.

    :param volume_root: Optional root directory for host volumes.
    :type volume_root: unicode
    """
    def __init__(self, volume_root=None):
        self._root = volume_root
        super(HostVolumeConfiguration, self).__init__()

    def __repr__(self):
        return '{0} shares: {1}'.format(self.__class__.__name__, self._map)

    @property
    def root(self):
        """
        Root directory for host volumes; if set, relative paths of host-shared directories will be prefixed with
        this.

        :return: Root directory for host volumes.
        :rtype: unicode
        """
        return self._root

    @root.setter
    def root(self, value):
        self._root = value

    def get(self, item, instance=None):
        value = super(HostVolumeConfiguration, self).get(item)
        if isinstance(value, dict):
            path = value.get(instance or 'default')
        else:
            path = value
        if path and self._root and (path[0] != posixpath.sep):
            return posixpath.join(self._root, path)
        return path

    def update(self, other=None, **kwargs):
        if other:
            if isinstance(other, HostVolumeConfiguration):
                self._root = other._root
            elif isinstance(other, dict):
                if 'root' in other:
                    other = other.copy()
                    self._root = other.pop('root')
            else:
                raise ValueError("Expected ContainerMap or dictionary; found '{0}'".format(type(other)))
        if 'root' in kwargs:
            self._root = kwargs.pop('root')
        super(HostVolumeConfiguration, self).update(other=other, **kwargs)

    def merge(self, items):
        if isinstance(items, HostVolumeConfiguration):
            self._map.update(items._map)
        elif isinstance(items, dict):
            if 'root' in items:
                items = items.copy()
                items.pop('root')
            self._map.update(items)
        else:
            raise ValueError("Expected ContainerMap or dictionary; found '{0}'".format(type(items)))
