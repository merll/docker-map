# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple
import operator
import posixpath
import six

from docker.client import DEFAULT_DOCKER_API_VERSION, DEFAULT_TIMEOUT_SECONDS

from . import DictMap
from .base import DockerClientWrapper


SINGLE_ATTRIBUTES = 'image', 'user', 'permissions', 'persistent'
DICT_ATTRIBUTES = 'create_options', 'start_options'
LIST_ATTRIBUTES = 'instances', 'shares', 'uses', 'attaches', 'clients'

HostShare = namedtuple('HostShare', ('volume', 'readonly'))
ContainerLink = namedtuple('ContainerLink', ('container', 'alias'))
PortBinding = namedtuple('PortBinding', ('exposed_port', 'host_port', 'interface'))


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
    if isinstance(value, HostShare):
        return value
    elif isinstance(value, six.string_types):
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
    if isinstance(value, ContainerLink):
        return value
    elif isinstance(value, six.string_types):
        return ContainerLink(value, value)
    elif isinstance(value, (list, tuple)):
        if len(value) == 2:
            return ContainerLink(*value)
        raise ValueError("Invalid element length; only tuples and lists of length 2 can be converted to a ContainerLink tuple.")
    raise ValueError("Invalid type; expected a list, tuple, or string type, found {0}.".format(type(value)))


def _get_port_binding(value):
    sub_types = six.string_types + (int, long)
    if isinstance(value, PortBinding):
        return value
    elif isinstance(value, sub_types):  # Port only
        return PortBinding(value, None, None)
    elif isinstance(value, (list, tuple)):  # Exposed port, host port, and possibly interface
        if len(value) == 1 and isinstance(value[0], sub_types):
            return PortBinding(value[0], None, None)
        if len(value) == 2:
            ex_port, host_bind = value
            if isinstance(host_bind, sub_types) or host_bind is None:  # Port, host port
                return PortBinding(ex_port, host_bind, None)
            elif isinstance(host_bind, (list, tuple)) and len(host_bind) == 2:  # Port, (host port, interface)
                host_port, interface = host_bind
                return PortBinding(ex_port, host_port, interface)
            raise ValueError("Invalid sub-element type or length. Needs to be a port number or a tuple / list: (port, interface).")
        elif len(value) == 3:
            ex_port, host_port, interface = value
            return PortBinding(ex_port, host_port, interface)
        raise ValueError("Invalid element length; only tuples and lists of length 2 or 3 can be converted to a PortBinding tuple.")
    raise ValueError("Invalid type; expected a list, tuple, int or string type, found {0}.".format(type(value)))


_get_host_shares = lambda value: _get_listed_tuples(value, HostShare, _get_host_share)
_get_container_links = lambda value: _get_listed_tuples(value, ContainerLink, _get_container_link)
_get_port_bindings = lambda value: _get_listed_tuples(value, PortBinding, _get_port_binding)


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
        self._exposes = []
        self._user = None
        self._permissions = None
        self._persistent = False
        self._clients = None
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
        :rtype: list[unicode]
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
        :rtype: list[unicode]
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
        :rtype: list[HostShare]
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
        :rtype: list[unicode]
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
        :rtype: list[ContainerLink]
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
        :rtype: list[unicode]
        """
        return self._attaches

    @attaches.setter
    def attaches(self, value):
        self._attaches = _get_list(value)

    @property
    def exposes(self):
        """
        Ports and (virtual) interface name that a network service is exposed on.

        The following formats are considered as valid input and will be converted to a list of ``PortBinding`` tuples:

        * Dictionary with container exposed ports as keys, and either host port and interface, or only the host port as
          values.
        * A list or tuple with elements

          * tuple or list: container exposed port, host port - for mapping all host addresses;
          * tuple or list: container exposed port, (host port, host interface) as nested tuple or list;
          * tuple or list: container exposed port, host port, host interface;
          * container exposed port only - will not be published, but is available to linked containers.

        If the host port, but no interface is set, the port will be published to all interfaces (as this is the Docker
        default). Otherwise the relevant IP address to expose the service on will be looked up at run-time.

        :return: List of port bindings.
        :rtype: list[PortBinding]
        """
        return self._exposes

    @exposes.setter
    def exposes(self, value):
        self._exposes = _get_port_bindings(value)

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
        Set this to ``True`` for containers that are only started to share a volume, but exist immediately.
        Such containers are restarted and not removed during cleanup.

        :return: Persistent flag.
        :rtype: bool
        """
        return self._persistent

    @persistent.setter
    def persistent(self, value):
        self._persistent = bool(value)

    @property
    def clients(self):
        """
        Set this to client names that you would like to limit container instantiation to. This overrides clients
        specified globally for a map.

        :return: Container configuration clients.
        :rtype: list[unicode]
        """
        return self._clients

    @clients.setter
    def clients(self, value):
        self._clients = list(value)

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

    def merge(self, values, lists_only=False):
        """
        Merges list-based attributes (instances, shares, uses, attaches, volumes, and binds) into one list including
        unique elements from both lists. When ``lists_only`` is set to ``False``, updates dictionaries and overwrites
        single-value attributes.

        :param values: Values to update the ContainerConfiguration with.
        :type values: ContainerConfiguration or dict
        :param lists_only: Ignore single-value attributes and update dictionary options.
        :type lists_only: bool
        """
        def _get_converted_list(dict_key, func):
            v = values.get(dict_key)
            if v:
                return func(v)
            return None

        def _merge_first(current, update_list):
            if not update_list:
                return
            new_keys = set(map(operator.itemgetter(0), update_list)) - set(map(operator.itemgetter(0), current))
            current.extend(filter(lambda u: u[0] in new_keys, update_list))

        def _update_attr(attr, update_func):
            update = get_func(attr)
            if update:
                update_func(attr, update)

        def _merge_list(attr, update_list):
            current = self.__getattribute__(attr)
            current.extend(set(update_list) - set(current))

        _update_single = lambda attr, new_val: self.__setattr__(attr, new_val)

        def _update_dict(attr, new_val):
            current_dict = self.__getattribute__(attr)
            if current_dict:
                current_dict.update(new_val)
            else:
                self.__setattr__(attr, new_val)

        if isinstance(values, dict):
            get_func = values.get
            update_binds = _get_converted_list('binds', _get_host_shares)
            update_links = _get_converted_list('links', _get_container_links)
            update_ports = _get_converted_list('publishes', _get_port_bindings)
        elif isinstance(values, ContainerConfiguration):
            get_func = values.__getattribute__
            update_binds = values._binds
            update_links = values._links_to
            update_ports = values._exposes
        else:
            raise ValueError("ContainerConfiguration or dictionary expected; found '{0}'.".format(type(values)))

        for key in LIST_ATTRIBUTES:
            _update_attr(key, _merge_list)
        _merge_first(self._binds, update_binds)
        _merge_first(self._links_to, update_links)
        _merge_first(self._exposes, update_ports)
        if not lists_only:
            for key in SINGLE_ATTRIBUTES:
                _update_attr(key, _update_single)
            for key in DICT_ATTRIBUTES:
                _update_attr(key, _update_dict)


class HostVolumeConfiguration(DictMap):
    """
    Class for storing volumes, as shared from the host with Docker containers.

    :param volume_root: Optional root directory for host volumes.
    :type volume_root: unicode
    """
    def __init__(self, volume_root=None, *args, **kwargs):
        self._root = volume_root
        super(HostVolumeConfiguration, self).__init__(*args, **kwargs)

    def __repr__(self):
        return '{0} shares: {1}'.format(self.__class__.__name__, self)

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


class ClientConfiguration(DictMap):
    """
    Configuration class for storing values that are specific to a particular Docker client, and generating client
    instances.

    :param base_url: URL of the Docker Remote API.
    :type base_url: unicode
    :param version: Docker Remote API version.
    :type version: unicode
    :param timeout: Request timeout.
    :type timeout: int
    :param args: Further initializing dictionary with values.
    :param kwargs: Further initializing keyword arguments.
    """
    init_kwargs = 'base_url', 'version', 'timeout', 'tls'
    client_constructor = DockerClientWrapper

    def __init__(self, base_url=None, version=DEFAULT_DOCKER_API_VERSION, timeout=DEFAULT_TIMEOUT_SECONDS,
                 *args, **kwargs):
        self.base_url = base_url
        self.version = version
        self.timeout = timeout
        if 'interfaces' in kwargs:
            self._interfaces = DictMap(kwargs.pop('interfaces'))
        else:
            self._interfaces = DictMap()
        self._client = kwargs.pop('client', None)
        super(ClientConfiguration, self).__init__(*args, **kwargs)

    @classmethod
    def from_client(cls, client):
        """
        Constructs a configuration object from an existing client instance.

        :param client: Client object to derive the configuration from.
        :type client: docker.client.Client
        :return: ClientConfiguration
        """
        return cls(base_url=client.base_url, version=client._version, timeout=client._timeout, client=client)

    def get_init_kwargs(self):
        """
        Generates keyword arguments for creating a new Docker client instance.

        :return: Keyword arguments as defined through this configuration.
        :rtype: dict
        """
        def _if_set():
            for k in self.init_kwargs:
                v = self.get(k)
                if v:
                    yield k, v

        return dict(_if_set())

    def get_client(self):
        """
        Retrieves or creates a client instance from this configuration object. If instantiated from this configuration,
        the resulting object is also cached in the property ``client``.

        :return: Client object instance.
        :rtype: docker.client.Client
        """
        client = self._client
        if not client:
            client = self.client_constructor(**self.get_init_kwargs())
            self._client = client
        return client

    @property
    def interfaces(self):
        """
        Dictionary of network interface settings as specific for the client. Note that the interface name is virtual,
        i.e. only used for assigning addresses.

        :return: Network interface configuration.
        :rtype: DictMap
        """
        return self._interfaces

    @interfaces.setter
    def interfaces(self, value):
        self._interfaces = DictMap(value)

    @property
    def client(self):
        """
        Assigned Client instance.

        :return: Client object.
        :rtype: docker.client.Client
        """
        return self._client

    @client.setter
    def client(self, value):
        self._client = value
