# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple
import six

from . import DictMap


def _get_list(value):
    if value is None:
        return []
    elif isinstance(value, (list, tuple)):
        return list(value)
    elif isinstance(value, six.string_types):
        return [value]
    raise ValueError("Invalid type; expected a list, tuple, or string type, found {0}.".format(type(value)))


HostBind = namedtuple('HostBind', ('volume', 'writeable'))
ContainerLink = namedtuple('ContainerLink', ('container', 'alias'))


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
        Returns the base image of the container.

        :return: Base image name.
        :rtype: unicode
        """
        return self._image

    @image.setter
    def image(self, value):
        """
        Sets the base image of the container. If set to `None`, the containers will be instantiated with an image that
        has the same name.

        :param value: Base image name.
        :type value: unicode
        """
        self._image = value

    @property
    def instances(self):
        """
        Returns the separate instances of a container, if any.

        :return: Instance names.
        :rtype: list
        """
        return self._instances

    @instances.setter
    def instances(self, value):
        """
        Sets separate instances for a container. By default there is one instance of each container. If set, containers
        will be created for each instance in the format `map_name.container_name.instance`.

        :param value: Instance names.
        :type value: list, tuple, unicode, or None
        """
        self._instances = _get_list(value)

    @property
    def shares(self):
        """
        Returns the shared volumes for a container.

        :return: Shared volumes.
        :rtype: list
        """
        return self._shares

    @shares.setter
    def shares(self, value):
        """
        Sets the shared volumes for a container.

        :param value: Shared volumes
        :type value: list, tuple, unicode, or None
        """
        self._shares = _get_list(value)

    @property
    def binds(self):
        """
        Returns the host volume binds for a container.

        :return: Host binds.
        :rtype: list
        """
        return self._binds

    @binds.setter
    def binds(self, value):
        """
        Sets the host volume binds for a container. These will be added to the shared volumes, and mapped to a host
        volume on container start. Each bind should be an instance of :class:`HostBind` with parameters
        `(volume_alias: unicode, write_access: bool)`.

        :param value: Host binds.
        :type value: list, tuple, HostBind, or None
        """
        if isinstance(value, HostBind):
            self._binds = [value]
        else:
            self._binds = _get_list(value)

    @property
    def uses(self):
        """
        Returns the volumes used from other containers.

        :return: Used volumes.
        :rtype: list
        """
        return self._uses

    @uses.setter
    def uses(self, value):
        """
        Sets the volumes used from other containers. This can be a combination of attached volume aliases, and container
        names if all volumes are to be used of that container.

        :param value: Used volumes.
        :type value: list, tuple, unicode or None
        """
        self._uses = _get_list(value)

    @property
    def links(self):
        """
        Returns linked containers.

        :return: Containers to be linked to when the container is started.
        :rtype: list
        """
        return self._links_to

    @links.setter
    def links(self, value):
        """
        Sets linked containers. Links are set in the format `ContainerLink(name, alias)`, where the name is the linked
        container's name, and the alias name the alias to use for this container instance.

        :param value: Containers to be linked to when the container is started.
        :type value: list, tuple, ContainerLink, or None
        """
        if isinstance(value, ContainerLink):
            self._links_to = [value]
        else:
            self._links_to = _get_list(value)

    @property
    def attaches(self):
        """
        Returns the names of containers that are attached to instances of this one.

        :return: Attached containers.
        :rtype: list
        """
        return self._attaches

    @attaches.setter
    def attaches(self, value):
        """
        Sets the names of container that are attached to instances of this one. If set, an empty container will be
        created with the purpose of sharing a volume. This volume is automatically shared with this one, but also
        available to other containers.

        :param value: Attached containers.
        :type value: list, tuple, unicode, or None
        """
        self._attaches = _get_list(value)

    @property
    def user(self):
        """
        Returns the user name / group or id to launch the container with and to which the owner is set in attached
        containers.

        :return: User name and (optional) group.
        :rtype: unicode, tuple, or int
        """
        return self._user

    @user.setter
    def user(self, value):
        """
        Sets the user name / group or id to launch the container with and to which the owner is set in attached
        containers. Can be set as a string (`user_name` or `user_name:group`), ids (e.g. `user_id:group_id`), tuple
        (`(user_name, group_name)`), or int (`user_id`).

        :param value: User name and (optional) group.
        :type value: unicode, tuple, or int
        """
        self._user = value

    @property
    def permissions(self):
        """
        Returns the permission flags to be set for attached volumes.

        :return: Permission flags.
        :rtype: unicode
        """
        return self._permissions

    @permissions.setter
    def permissions(self, value):
        """
        Sets the permission flags to be set for attached volumes. Can be in any notation accepted by `chmod`.

        :param value: Permission flags.
        :type value: unicode
        """
        self._permissions = value

    @property
    def create_options(self):
        """
        Returns additional keyword args for :func:`docker.client.Client.create_container`.

        :return: Kwargs for creating the container.
        :rtype: dict
        """
        return self._create_kwargs

    @create_options.setter
    def create_options(self, value):
        """
        Sets additional keyword args for :func:`docker.client.Client.create_container`.

        :param value: Kwargs for creating the container.
        :type value: dict
        """
        self._create_kwargs = value

    @property
    def start_options(self):
        """
        Returns additional keyword args for :func:`docker.client.Client.start`.

        :return: Kwargs for starting the container.
        :rtype: dict
        """
        return self._start_kwargs

    @start_options.setter
    def start_options(self, value):
        """
        Sets additional keyword args for :func:`docker.client.Client.start`.

        :param value: Kwargs for starting the container.
        :type value: dict
        """
        self._start_kwargs = value

    def update(self, values):
        """
        Updates the container configuration with the contents of the given dictionary, if keys are valid attributes for
        this class.

        :param values: Dictionary to update this container configuration with.
        :type values: dict
        """
        for key, value in six.iteritems(values):
            if hasattr(self, key):
                self.__setattr__(key, value)


class HostVolumeConfiguration(DictMap):
    """
    Class for storing volumes, as shared from the host with Docker containers.
    """
    def __repr__(self):
        return '{0} shares: {1}'.format(self.__class__.__name__, self._map)
