# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from ..input import (get_list, get_shared_volumes, get_shared_host_volumes, get_container_links, get_network_mode,
                     get_port_bindings, get_exec_commands, merge_list, NotSet)

SINGLE_ATTRIBUTES = 'image', 'user', 'permissions', 'persistent', 'stop_timeout', 'stop_signal', 'network'
DICT_ATTRIBUTES = 'create_options', 'start_options', 'host_config'
LIST_ATTRIBUTES = 'instances', 'shares', 'attaches', 'clients'


class ContainerConfiguration(object):
    """
    Class to maintain resources that are associated with a container.

    :param kwargs: Optional initial values.
    """
    def __init__(self, **kwargs):
        self._abstract = None
        self._extends = []
        self._image = NotSet
        self._instances = []
        self._shares = []
        self._binds = []
        self._uses = []
        self._links_to = []
        self._attaches = []
        self._exposes = []
        self._exec = []
        self._user = NotSet
        self._permissions = NotSet
        self._persistent = NotSet
        self._clients = NotSet
        self._create_kwargs = NotSet
        self._host_config_kwargs = NotSet
        self._stop_timeout = NotSet
        self._stop_signal = NotSet
        self._network = NotSet
        self.update(kwargs)

    def __repr__(self):
        if self._extends:
            ext_str = 'extends {0}'.format(self._extends)
        else:
            ext_str = ''
        return ("{1}{0.__class__.__name__} {2} shares: {0._shares}; binds: {0._binds}; uses: {0._uses}; "
                "attaches: {0._attaches}").format(self, 'Abstract ' if self._abstract else '', ext_str)

    @property
    def abstract(self):
        return self._abstract

    @abstract.setter
    def abstract(self, value):
        self._abstract = bool(value)

    @property
    def extends(self):
        """

        :return:
        :rtype: list[unicode | str]
        """
        return self._extends

    @extends.setter
    def extends(self, value):
        self._extends = get_list(value)

    @property
    def image(self):
        """
        The base image of the container. If set to `None`, the containers will be instantiated with an image that
        has the same name.

        :return: Base image name.
        :rtype: unicode | str
        """
        return self._image

    @image.setter
    def image(self, value):
        self._image = value

    @image.deleter
    def image(self):
        self._image = NotSet

    @property
    def instances(self):
        """
        Separate instances of a container, if any. By default there is one instance of each container. If set,
        containers will be created for each instance in the format `map_name.container_name.instance`.

        :return: Instance names.
        :rtype: list[unicode | str]
        """
        return self._instances

    @instances.setter
    def instances(self, value):
        self._instances = get_list(value)

    @property
    def shares(self):
        """
        Shared volumes for a container.

        :return: Shared volumes.
        :rtype: list[unicode | str]
        """
        return self._shares

    @shares.setter
    def shares(self, value):
        self._shares = get_list(value)

    @property
    def binds(self):
        """
        Returns the host volume shares for a container. These will be added to the shared volumes, and mapped to a host
        volume on container start.

        :return: Host volumes.
        :rtype: list[dockermap.map.input.SharedVolume]
        """
        return self._binds

    @binds.setter
    def binds(self, value):
        self._binds = get_shared_host_volumes(value)

    @property
    def uses(self):
        """
        Volumes used from other containers. This can be a combination of attached volume aliases, and container
        names if all volumes are to be used of that container.

        :return: Used volumes.
        :rtype: list[dockermap.map.input.SharedVolume]
        """
        return self._uses

    @uses.setter
    def uses(self, value):
        self._uses = get_shared_volumes(value)

    @property
    def links(self):
        """
        Linked containers. Links are set in the format `ContainerLink(name, alias)`, where the name is the linked
        container's name, and the alias name the alias to use for this container instance.

        :return: Containers to be linked to when the container is started.
        :rtype: list[dockermap.map.input.ContainerLink]
        """
        return self._links_to

    @links.setter
    def links(self, value):
        self._links_to = get_container_links(value)

    @property
    def attaches(self):
        """
        Names of containers that are attached to instances of this one. If set, an empty container will be
        created with the purpose of sharing a volume. This volume is automatically shared with this one, but also
        available to other containers.

        :return: Attached containers.
        :rtype: list[unicode | str]
        """
        return self._attaches

    @attaches.setter
    def attaches(self, value):
        self._attaches = get_list(value)

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
        :rtype: list[dockermap.map.input.PortBinding]
        """
        return self._exposes

    @exposes.setter
    def exposes(self, value):
        self._exposes = get_port_bindings(value)

    @property
    def exec_commands(self):
        """
        Commands to run as soon as the container is started. Set in the format `ExecCommand(cmd, user, policy)`, where
        the user is set to the same as this configuration's user by default (or root, if not available). The policy
        decides when to start the command.

        :return: Commands to run when the container is started.
        :rtype: list[dockermap.map.input.ExecCommand]
        """
        return self._exec

    @exec_commands.setter
    def exec_commands(self, value):
        self._exec = get_exec_commands(value)

    @property
    def user(self):
        """
        User name / group or id to launch the container with and to which the owner is set in attached
        containers. Can be set as a string (`user_name` or `user_name:group`), ids (e.g. `user_id:group_id`), tuple
        (`(user_name, group_name)`), or int (`user_id`).

        :return: User name and (optional) group.
        :rtype: unicode | str | tuple | int
        """
        return self._user

    @user.setter
    def user(self, value):
        self._user = value

    @user.deleter
    def user(self):
        self._user = NotSet

    @property
    def permissions(self):
        """
        Permission flags to be set for attached volumes. Can be in any notation accepted by `chmod`.

        :return: Permission flags.
        :rtype: unicode | str
        """
        return self._permissions

    @permissions.setter
    def permissions(self, value):
        self._permissions = value

    @permissions.deleter
    def permissions(self):
        self._permissions = NotSet

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
        if value is NotSet:
            self._persistent = NotSet
        else:
            self._persistent = bool(value)

    @persistent.deleter
    def persistent(self):
        self._persistent = NotSet

    @property
    def clients(self):
        """
        Set this to client names that you would like to limit container instantiation to. This overrides clients
        specified globally for a map.

        :return: Container configuration clients.
        :rtype: list[unicode | str]
        """
        return self._clients

    @clients.setter
    def clients(self, value):
        self._clients = get_list(value)

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
    def host_config(self):
        """
        Additional keyword args for :meth:`docker.client.Client.start` or HostConfig options to pass to
        :meth:`docker.client.Client.create`.

        :return: Kwargs for creating the HostConfig dict or starting the container.
        :rtype: dict
        """
        return self._host_config_kwargs

    @host_config.setter
    def host_config(self, value):
        self._host_config_kwargs = value

    start_options = host_config

    @property
    def stop_timeout(self):
        """
        Individual timeout (in seconds) for stopping a container, i.e. the time between sending a ``SIGTERM`` and a
        ``SIGKILL`` to the container.

        :return: Container stop timeout.
        :rtype: int
        """
        return self._stop_timeout

    @stop_timeout.setter
    def stop_timeout(self, value):
        self._stop_timeout = value

    @stop_timeout.deleter
    def stop_timeout(self):
        self._stop_timeout = NotSet

    @property
    def stop_signal(self):
        """
        By default Docker sends ``SIGTERM`` to containers on stop or restart. This may not always be the best signal
        to get the main process to shut down properly. This property can for example be set to ``SIGINT``, where
        more appropriate.

        :return: Stop signal.
        :rtype: int | unicode | str
        """
        return self._stop_signal

    @stop_signal.setter
    def stop_signal(self, value):
        self._stop_signal = value

    @stop_signal.deleter
    def stop_signal(self):
        self._stop_signal = NotSet

    @property
    def network(self):
        """
        Networking to apply to this container. If not ``bridge`` or ``host`` (as described in the docker-py
        docs), tries to locate a container configuration on this map. Prefixed with ``/`` assumes the full container
        name. Setting it to ``disabled`` deactivates networking for the container.

        :return: Container networking setting.
        :rtype: unicode | str
        """
        return self._network

    @network.setter
    def network(self, value):
        self._network = get_network_mode(value)

    @network.deleter
    def network(self):
        self._network = NotSet

    def update(self, values):
        """
        Updates the container configuration with the contents of the given configuration object or dictionary. In case
        of a dictionary, only valid attributes for this class are considered. Existing attributes are replaced with
        the new values.

        :param values: Dictionary or ContainerConfiguration object to update this container configuration with.
        :type values: dict | ContainerConfiguration
        """
        if isinstance(values, ContainerConfiguration):
            self._abstract = values._abstract
            self._extends = values._extends[:]
            self._image = values._image
            self._instances = values._instances[:]
            self._shares = values._shares[:]
            self._binds = values._binds[:]
            self._uses = values._uses[:]
            self._links_to = values._links_to[:]
            self._attaches = values._attaches[:]
            self._exposes = values._exposes[:]
            self._exec = values._exec[:]
            self._user = values._user
            self._permissions = values._permissions
            self._persistent = values._persistent
            if values._clients is NotSet:
                self._clients = NotSet
            else:
                self._clients = values._clients[:]
            if values._create_kwargs is NotSet:
                self._create_kwargs = NotSet
            else:
                self._create_kwargs = values._create_kwargs.copy()
            if values._host_config_kwargs is NotSet:
                self._host_config_kwargs = NotSet
            else:
                self._host_config_kwargs = values._host_config_kwargs.copy()
            self._stop_timeout = values._stop_timeout
            self._stop_signal = values._stop_signal
            self._network = values._network
        elif isinstance(values, dict):
            for key, value in six.iteritems(values):
                if hasattr(self, key):
                    setattr(self, key, value)
        else:
            raise ValueError("ContainerConfiguration or dictionary expected; found '{0}'.".format(type(values).__name__))

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
            new_keys = set(item[0] for item in update_list) - set(item[0] for item in current)
            current.extend(u for u in update_list if u[0] in new_keys)

        def _update_attr(attr, update_func):
            update = get_func(attr)
            if update is not None and update is not NotSet:
                update_func(attr, update)

        def _merge_converted_list(attr, updates):
            current = getattr(self, attr)
            merge_list(get_list(updates), current)

        def _merge_list(attr, update_list):
            current = getattr(self, attr)
            merge_list(update_list, current)

        def _update_dict(attr, new_val):
            current_dict = getattr(self, attr)
            if current_dict:
                current_dict.update(new_val)
            elif new_val:
                setattr(self, attr, new_val.copy())

        if isinstance(values, dict):
            get_func = values.get
            update_binds = _get_converted_list('binds', get_shared_host_volumes)
            update_uses = _get_converted_list('uses', get_shared_volumes)
            update_links = _get_converted_list('links', get_container_links)
            update_ports = _get_converted_list('exposes', get_port_bindings)
            update_cmds = _get_converted_list('exec_commands', get_exec_commands)
            merge_list_func = _merge_converted_list
        elif isinstance(values, ContainerConfiguration):
            get_func = values.__getattribute__
            update_binds = values._binds
            update_uses = values._uses
            update_links = values._links_to
            update_ports = values._exposes
            update_cmds = values._exec
            merge_list_func = _merge_list
        else:
            raise ValueError("ContainerConfiguration or dictionary expected; found '{0}'.".format(type(values).__name__))

        for key in LIST_ATTRIBUTES:
            _update_attr(key, merge_list_func)
        _merge_first(self._binds, update_binds)
        _merge_first(self._uses, update_uses)
        _merge_first(self._exposes, update_ports)
        _merge_list('_links_to', update_links)
        _merge_list('_exec', update_cmds)
        if not lists_only:
            for key in SINGLE_ATTRIBUTES:
                _update_attr(key, self.__setattr__)
            for key in DICT_ATTRIBUTES:
                _update_attr(key, _update_dict)
