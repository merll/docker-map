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
        Returns the host volume binds for a container. These will be added to the shared volumes, and mapped to a host
        volume on container start. Each bind should be an instance of :class:`HostBind` with parameters
        `(volume_alias: unicode, write_access: bool)`.

        :return: Host binds.
        :rtype: list
        """
        return self._binds

    @binds.setter
    def binds(self, value):
        if isinstance(value, HostBind):
            self._binds = [value]
        else:
            self._binds = _get_list(value)

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
        if isinstance(value, ContainerLink):
            self._links_to = [value]
        else:
            self._links_to = _get_list(value)

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
    def create_options(self):
        """
        Additional keyword args for :func:`docker.client.Client.create_container`.

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
        Additional keyword args for :func:`docker.client.Client.start`.

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
