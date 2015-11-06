# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod
from six import with_metaclass, iteritems, text_type
import logging
import signal
from docker.utils.utils import create_host_config

from ... import DEFAULT_COREIMAGE, DEFAULT_BASEIMAGE
from ...functional import resolve_value
from ..input import NotSet, EXEC_POLICY_INITIAL
from . import ACTION_DEPENDENCY_FLAG
from .dep import ContainerDependencyResolver
from .cache import ContainerCache, ImageCache
from .utils import (extract_user, get_host_binds, get_port_bindings, get_volumes, init_options, update_kwargs,
                    use_host_config, get_instance_volumes, get_preparation_cmd)


log = logging.getLogger(__name__)


class BasePolicy(with_metaclass(ABCMeta, object)):
    """
    Abstract base class providing the basic infrastructure for generating actions based on container state.

    :param container_maps: Container maps.
    :type container_maps: dict[unicode | str, dockermap.map.container.ContainerMap]
    :param clients: Dictionary of clients.
    :type clients: dict[unicode | str, dockermap.map.config.ClientConfiguration]
    """
    core_image = DEFAULT_COREIMAGE
    base_image = DEFAULT_BASEIMAGE

    def __init__(self, container_maps, clients):
        self._maps = {
            map_name: map_contents.get_extended_map()
            for map_name, map_contents in iteritems(container_maps)
        }
        self._clients = clients
        self._container_names = ContainerCache(clients)
        self._images = ImageCache(clients)
        self._f_resolver = ContainerDependencyResolver()
        for m in self._maps.values():
            self._f_resolver.update(m)
        self._r_resolver = ContainerDependencyResolver()
        for m in self._maps.values():
            self._r_resolver.update_backward(m)

    @classmethod
    def get_default_client_name(cls):
        """
        Determines a default client name.

        :return: Default client name.
        """
        return '__default__'

    @classmethod
    def cname(cls, map_name, container, instance=None):
        """
        Generates a container name that should be used for creating new containers and checking the status of existing
        containers.

        In this implementation, the format will be ``<map name>.<container name>.<instance>`` name. If no instance is
        provided, it is just ``<map name>.<container name>``.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instance: Instance name (optional).
        :type instance: unicode | str
        :return: Container name.
        :rtype: unicode | str
        """
        if instance:
            return '{0}.{1}.{2}'.format(map_name, container, instance)
        return '{0}.{1}'.format(map_name, container)

    @classmethod
    def aname(cls, map_name, attached_name, parent_name=None):
        """
        Generates a container name that should be used for creating new attached volume containers and checking the
        status of existing containers.

        In this implementation, the format will be ``<map name>.<attached>``, or ``<map name>.<parent name>.<attached>``
        if the parent container configuration name is provided.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param attached_name: Attached container alias.
        :type attached_name: unicode | str
        :param parent_name: Container configuration name that has contains attached container.
        :type parent_name: unicode | str
        :return: Container name.
        :rtype: unicode | str
        """
        if parent_name:
            return '{0}.{1}.{2}'.format(map_name, parent_name, attached_name)
        return '{0}.{1}'.format(map_name, attached_name)

    @classmethod
    def resolve_cname(cls, container_name, includes_map=True):
        """
        The reverse function of :meth:`cname` for resolving a container name into map name, container configuration,
        and instance name. The instance name may be ``None`` if not present. In case the map name is not present
        in the container name, ``includes_map`` should be set to ``False`` for only resolving configuration name and map
        name.

        :param container_name: Container name.
        :type container_name: unicode | str
        :param includes_map: Whether the name includes a map name (e.g. for running containers) or not (e.g. for
         references within the same map).
        :return: Tuple of container map name (optional), container configuration name, and instance.
        :rtype: tuple[unicode | str]
        """
        if includes_map:
            map_name, __, ci_name = container_name.partition('.')
            if not ci_name:
                raise ValueError("Invalid container name: {0}".format(container_name))
            c_name, __, i_name = ci_name.partition('.')
            return map_name, c_name, i_name or None

        c_name, __, i_name = container_name.partition('.')
        return c_name, i_name or None

    @classmethod
    def iname(cls, container_map, image):
        """
        Generates the full image name that should be used when creating a new container.

        This implementation applies the following rules:

        * If the image name starts with ``/``, the following image name is returned.
        * If ``/`` is found anywhere else in the image name, it is assumed to be a repository-prefixed image and
          returned as it is.
        * Otherwise, if the given container map has a repository prefix set, this is prepended to the image name.
        * In any other case, the image name is returned unmodified.

        In any case this method is indifferent to whether a tag is appended or not. Docker by default uses the image
        with the ``latest`` tag.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param image: Image name.
        :type image: unicode | str.
        :return: Image name, where applicable prefixed with a repository.
        :rtype: unicode | str
        """
        if '/' in image:
            if image[0] == '/':
                return image[1:]
            return image
        repository = resolve_value(container_map.repository)
        if repository:
            return '{0}/{1}'.format(repository, image)
        return image

    @classmethod
    def get_hostname(cls, client_name, container_name):
        """
        Generates a host name from the container name and the client configuration name.

        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param container_name: Container name.
        :type container_name: unicode | str
        """
        if client_name == cls.get_default_client_name():
            return container_name
        return '{0}-{1}'.format(container_name, client_name)

    @classmethod
    def get_domainname(cls, container_map, container_config, client_config):
        """
        Provides a domain name for the container, either from the client configuration or the container map default.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        """
        return resolve_value(client_config.get('domainname', container_map.default_domain))

    @classmethod
    def get_create_kwargs(cls, container_map, config_name, container_config, client_name, client_config, container_name,
                          instance, include_host_config=True, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create a container.

        :param config_name:
        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name.
        :type container_name: unicode | str
        :param instance: Instance name.
        :type instance: unicode | str | NoneType
        :param include_host_config: Whether to generate and include the HostConfig.
        :type include_host_config: Set to ``False``, if calling :meth:`get_start_kwargs:` later.
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            name=container_name,
            image=cls.iname(container_map, container_config.image or config_name),
            volumes=get_volumes(container_map, container_config),
            user=extract_user(container_config.user),
            ports=[resolve_value(port_binding.exposed_port)
                   for port_binding in container_config.exposes if port_binding.exposed_port],
            hostname=cls.get_hostname(client_name, container_name) if container_map.set_hostname else None,
            domainname=cls.get_domainname(container_map, container_config, client_config),
        )
        if container_config.network == 'disabled':
            c_kwargs['network_disabled'] = True
        hc_extra_kwargs = kwargs.pop('host_config', None) if kwargs else None
        if include_host_config:
            hc_kwargs = cls.get_host_config_kwargs(container_map, config_name, container_config, client_name,
                                                   client_config, None, instance, kwargs=hc_extra_kwargs)
            if hc_kwargs:
                c_kwargs['host_config'] = create_host_config(**hc_kwargs)
        update_kwargs(c_kwargs, init_options(container_config.create_options), kwargs)
        return c_kwargs

    @classmethod
    def get_host_config_kwargs(cls, container_map, config_name, container_config, client_name, client_config,
                               container_name, instance, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig or start a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name or id.
        :type container_name: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        def volume_str(u):
            vol = cls.cname(map_name, u.volume)
            if u.readonly:
                return '{0}:ro'.format(vol)
            return vol

        map_name = container_map.name
        volumes_from = list(map(volume_str, container_config.uses))
        if container_map.use_attached_parent_name:
            volumes_from.extend([cls.aname(map_name, attached, config_name)
                                 for attached in container_config.attaches])
        else:
            volumes_from.extend([cls.aname(map_name, attached)
                                 for attached in container_config.attaches])
        c_kwargs = dict(
            links=[(cls.cname(map_name, l_name), alias) for l_name, alias in container_config.links],
            binds=get_host_binds(container_map, container_config, instance),
            volumes_from=volumes_from,
            port_bindings=get_port_bindings(container_config, client_config),
            version=client_config.version,
        )
        network_mode = container_config.network
        if isinstance(network_mode, tuple):
            c_kwargs['network_mode'] = 'container:{0}'.format(cls.cname(map_name, *network_mode))
        elif isinstance(network_mode, text_type):
            c_kwargs['network_mode'] = network_mode
        if container_name:
            c_kwargs['container'] = container_name
        update_kwargs(c_kwargs, init_options(container_config.host_config), kwargs)
        return c_kwargs

    @classmethod
    def get_start_kwargs(cls, *args, **kwargs):
        """
        Same as :meth:`get_host_config_kwargs` for backwards compatibility.
        """
        return cls.get_host_config_kwargs(*args, **kwargs)

    @classmethod
    def get_attached_create_kwargs(cls, container_map, config_name, container_config, client_name, client_config,
                                   container_name, alias, include_host_config=True, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create an attached container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name.
        :type container_name: unicode | str
        :param alias: Alias name of the container volume.
        :type alias: unicode | str
        :param include_host_config: Whether to generate and include the HostConfig.
        :type include_host_config: Set to ``False``, if calling :meth:`get_start_kwargs:` later.
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        path = resolve_value(container_map.volumes[alias])
        user = extract_user(container_config.user)
        c_kwargs = dict(
            name=container_name,
            image=cls.base_image,
            volumes=[path],
            user=user,
            network_disabled=True,
        )
        hc_extra_kwargs = kwargs.pop('host_config', None) if kwargs else None
        if include_host_config:
            hc_kwargs = cls.get_attached_host_config_kwargs(container_map, config_name, container_config, client_name,
                                                            client_config, None, alias, kwargs=hc_extra_kwargs)
            if hc_kwargs:
                c_kwargs['host_config'] = create_host_config(**hc_kwargs)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_attached_host_config_kwargs(cls, container_map, config_name, container_config, client_name, client_config,
                                        container_name, alias, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig or start an attached container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name or id.
        :type container_name: unicode | str | NoneType
        :param alias: Alias name of the container volume.
        :type alias: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(version=client_config.version)
        if container_name:
            c_kwargs['container'] = container_name
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_attached_start_kwargs(cls, *args, **kwargs):
        """
        Same as :meth:`get_attached_host_config_kwargs` for backwards compatibility.
        """
        return cls.get_attached_host_config_kwargs(*args, **kwargs)

    @classmethod
    def get_attached_preparation_create_kwargs(cls, container_map, config_name, container_config, client_name,
                                               client_config, container_name, alias, volume_container,
                                               include_host_config=True, kwargs=None):
        """
        Generates keyword arguments for the Docker client to prepare an attached container (i.e. adjust user and
        permissions).

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name.
        :type container_name: unicode | str
        :param alias: Alias name of the container volume.
        :type alias: unicode | str
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode | str
        :param include_host_config: Whether to generate and include the HostConfig.
        :type include_host_config: Set to ``False``, if calling :meth:`get_start_kwargs:` later.
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        path = resolve_value(container_map.volumes[alias])
        cmd = get_preparation_cmd(container_config, path)
        if not cmd:
            return None
        c_kwargs = dict(
            image=cls.core_image,
            command=' && '.join(cmd),
            user='root',
            network_disabled=True,
        )
        hc_extra_kwargs = kwargs.pop('host_config', None) if kwargs else None
        if include_host_config:
            hc_kwargs = cls.get_attached_preparation_host_config_kwargs(container_map, config_name, container_config,
                                                                        client_name, client_config, None, alias,
                                                                        volume_container, kwargs=hc_extra_kwargs)
            if hc_kwargs:
                c_kwargs['host_config'] = create_host_config(**hc_kwargs)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_attached_preparation_host_config_kwargs(cls, container_map, config_name, container_config, client_name,
                                                    client_config, container_name, alias, volume_container,
                                                    kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig for preparing an attached container
        (i.e. adjust user and permissions) or start the preparation.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name or id.
        :type container_name: unicode | str | NoneType
        :param alias: Alias name of the container volume.
        :type alias: unicode | str
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(volumes_from=[volume_container], version=client_config.version)
        if container_name:
            c_kwargs['container'] = container_name
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_attached_preparation_start_kwargs(cls, *args, **kwargs):
        """
        Same as :meth:`get_attached_preparation_host_config_kwargs` for backwards compatibility.
        """
        return cls.get_attached_preparation_host_config_kwargs(*args, **kwargs)

    @classmethod
    def get_restart_kwargs(cls, container_map, config_name, container_config, client_name, client_config,
                           container_name, instance, kwargs=None):
        """
        Generates keyword arguments for the Docker client to restart a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param instance: Instance name.
        :type instance: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(container=container_name)
        if container_config.stop_timeout is NotSet:
            timeout = client_config.get('stop_timeout')
            if timeout is not None:
                c_kwargs['timeout'] = timeout
        else:
            c_kwargs['timeout'] = container_config.stop_timeout
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_stop_kwargs(cls, container_map, config_name, container_config, client_name, client_config, container_name,
                        instance, kwargs=None):
        """
        Generates keyword arguments for the Docker client to stop a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param instance: Instance name.
        :type instance: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            container=container_name,
        )
        if container_config.stop_timeout is NotSet:
            timeout = client_config.get('stop_timeout')
            if timeout is not None:
                c_kwargs['timeout'] = timeout
        else:
            c_kwargs['timeout'] = container_config.stop_timeout
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_remove_kwargs(cls, container_map, config_name, container_config, client_name, client_config, container_name,
                          kwargs=None):
        """
        Generates keyword arguments for the Docker client to remove a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(container=container_name)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_exec_create_kwargs(cls, container_map, config_name, container_config, client_name, client_config,
                               container_name, instance, exec_cmd, exec_user, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig or start a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name or id.
        :type container_name: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :param exec_cmd: Command to be executed.
        :type exec_cmd: unicode | str
        :param exec_user: User to run the command.
        :type exec_user: unicode | str
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            container=container_name,
            cmd=resolve_value(exec_cmd),
        )
        if exec_user is not None:
            c_kwargs['user'] = resolve_value(exec_user)
        elif container_config.user is not NotSet:
            c_kwargs['user'] = extract_user(container_config.user)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_exec_start_kwargs(cls, container_map, config_name, container_config, client_name, client_config,
                              container_name, instance, exec_id, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig or start a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name or id.
        :type container_name: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :param exec_id: Id of the exec instance.
        :type exec_id: long
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(exec_id=exec_id)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_clients(self, c_config, c_map):
        """
        Returns the Docker client objects for a given container configuration or map. If there are no clients specified
        for the configuration, the list defaults to the one globally specified for the given map. If that is not defined
        either, the default client is returned.

        :param c_config: Container configuration object.
        :type c_config: dockermap.map.config.ContainerConfiguration
        :param c_map: Container map instance.
        :type c_map: dockermap.map.container.ContainerMap
        :return: Docker client objects.
        :rtype: tuple[tuple[unicode | str, docker.client.Client, dockermap.map.config.ClientConfiguration]]
        """
        def _get_client(client_name):
            client_config = self._clients[client_name]
            return client_name, client_config.get_client(), client_config

        if c_config.clients:
            return tuple(map(_get_client, c_config.clients))
        if c_map.clients:
            return tuple(map(_get_client, c_map.clients))
        default_name = self.get_default_client_name()
        return _get_client(default_name),

    def get_dependencies(self, map_name, container):
        """
        Generates the list of dependency containers, in reverse order (i.e. the last dependency coming first).

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :return: Dependency container map names, container configuration names, and instances.
        :rtype: iterator[(unicode | str, unicode | str, unicode | str)]
        """
        return reversed(self._f_resolver.get_container_dependencies(map_name, container))

    def get_dependents(self, map_name, container):
        """
        Generates the list of dependent containers, in reverse order (i.e. the last dependent coming first).

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :return: Dependent container map names, container configuration names, and instances.
        :rtype: iterator[(unicode | str, unicode | str, unicode | str)]
        """
        return reversed(self._r_resolver.get_container_dependencies(map_name, container))

    @abstractmethod
    def create_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for the ``create`` command, which may involve any container action (create, start, stop,
        remove) as necessary. To be implemented by subclasses.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list | tuple | unicode | str
        :param kwargs: Additional keyword arguments to pass. Should only be applied to create actions, if any.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        pass

    @abstractmethod
    def start_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for the ``start`` command, which may involve any container action (create, start, stop,
        remove) as necessary. To be implemented by subclasses.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list | tuple | unicode | str
        :param kwargs: Additional keyword arguments to pass. Should only be applied to start actions, if any.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        pass

    @abstractmethod
    def stop_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for the ``stop`` command, which may involve any container action (create, start, stop,
        remove) as necessary. To be implemented by subclasses.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list | tuple | unicode | str
        :param kwargs: Additional keyword arguments to pass. Should only be applied to stop actions, if any.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        pass

    @abstractmethod
    def remove_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for the ``remove`` command, which may involve any container action (create, start, stop,
        remove) as necessary. To be implemented by subclasses.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list | tuple | unicode | str
        :param kwargs: Additional keyword arguments to pass. Should only be applied to remove actions, if any.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        pass

    def startup_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for a ``startup`` command, which may involve any container action (create, start, stop,
        remove) as necessary. Implementation by subclasses is optional.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list | tuple | unicode | str
        :param kwargs: Additional keyword arguments to pass.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        raise NotImplementedError("This policy does not support the startup command.")

    def shutdown_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for a ``shutdown`` command, which may involve any container action (create, start, stop,
        remove) as necessary. Implementation by subclasses is optional.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list | tuple | unicode | str
        :param kwargs: Additional keyword arguments to pass.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        raise NotImplementedError("This policy does not support the shutdown command.")

    def restart_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for the ``restart`` command, which may involve any container action (create, start, stop,
        remove) as necessary. Implementation by subclasses is optional.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list | tuple | unicode | str
        :param kwargs: Additional keyword arguments to pass.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        raise NotImplementedError("This policy does not support the restart command.")

    def update_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for the ``update`` command, which may involve any container action (create, start, stop,
        remove) as necessary. Implementation by subclasses is optional.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list | tuple | unicode | str
        :param kwargs: Additional keyword arguments to pass.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        raise NotImplementedError("This policy does not support the update command.")

    def run_script(self, map_name, container, instance=None, **kwargs):
        """
        Runs a single script or command in a container. Implementation is optional.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Container configuration name.
        :type container: unicode | str
        :param script_path: Path to the script on the Docker host.
        :param kwargs: Keyword arguments to the script runner function.
        :return: A dictionary of client names with their log output and exit codes.
        :rtype: dict[unicode | str, dict]
        """
        raise NotImplementedError("This policy does not support the script command.")

    @property
    def container_maps(self):
        """
        Container maps with container configurations to base actions on.

        :return: Dictionary of container maps.
        :rtype: dict[unicode | str, dockermap.map.container.ContainerMap]
        """
        return self._maps

    @property
    def clients(self):
        """
        Docker client objects and configurations.

        :return: Dictionary of Docker client objects.
        :rtype: dict[unicode | str, dockermap.map.config.ClientConfiguration]
        """
        return self._clients

    @property
    def container_names(self):
        """
        Names of existing containers on each map.

        :return: Dictionary of container names.
        :rtype: dict[unicode | str, dockermap.map.policy.cache.CachedContainerNames]
        """
        return self._container_names

    @property
    def images(self):
        """
        Image information functions.

        :return: Dictionary of image names per client.
        :rtype: dict[unicode | str, dockermap.map.policy.cache.CachedImages]
        """
        return self._images


class AbstractActionGenerator(with_metaclass(ABCMeta)):
    """
    Abstract base implementation for an action generator, which generates actions for a policy.

    :param policy: Policy object instance.
    :type policy: BasePolicy
    """
    def __init__(self, policy=None):
        self._policy = policy

    @abstractmethod
    def generate_item_actions(self, map_name, c_map, config_name, c_config, instances, flags, *args, **kwargs):
        """
        To be implemented by subclasses. Should generate the actions on a single item, which can be either a dependency
        or a explicitly selected container.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param c_map: Container map instance.
        :type c_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param c_config: Container configuration object.
        :type c_config: dockermap.map.config.ContainerConfiguration
        :param instances: Instance names as a list. Can be ``[None]``
        :type instances: list[unicode | str]
        :param flags: Flags for the current container, as defined in :mod:`~dockermap.map.policy.actions`.
        :type flags: int
        :param args: Additional positional arguments.
        :param kwargs: Additional keyword arguments.
        """
        pass

    def generate_actions(self, map_name, config_name, instance_name, c_flags=0, **c_kwargs):
        c_map = self._policy.container_maps[map_name]
        c_config = c_map.get_existing(config_name)
        if not c_config:
            raise KeyError("Container configuration '{0}' not found on map '{1}'.".format(
                config_name, map_name))
        c_instances = [instance_name] if instance_name else c_config.instances or [None]
        return self.generate_item_actions(map_name, c_map, config_name, c_config, c_instances, c_flags, **c_kwargs)

    def get_all_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates and performs actions for the selected container.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Main container configuration name.
        :type container: unicode | str
        :param instances: Instance names.
        :type instances: list or tuple
        :param kwargs: Additional keyword arguments to pass to the main container action.
        :return: Return values of created main containers.
        :rtype: list[(unicode | str, dict)]
        """
        return list(self.generate_actions(map_name, container, instances, c_flags=0, **kwargs) or ())

    @property
    def policy(self):
        """
        Policy object instance to generate actions for.

        :return: Policy object instance.
        :rtype: BasePolicy
        """
        return self._policy

    @policy.setter
    def policy(self, value):
        self._policy = value


class AbstractDependentActionGenerator(AbstractActionGenerator):
    """
    Abstract extension for an action generator, which generates actions for a policy, considering dependencies.
    """
    @abstractmethod
    def get_dependency_path(self, map_name, config_name):
        """
        To be implemented by subclasses (or using :class:`ForwardActionGeneratorMixin` or
        class:`ReverseActionGeneratorMixin`). Should provide an iterable of objects to be handled before the explicitly
        selected container configuration.

        :param map_name: Container map name.
        :param config_name: Container configuration name.
        :return: Iterable of dependency objects in tuples of map name, container (config) name, instance.
        :rtype: list[tuple]
        """
        pass

    def get_all_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates and performs actions for the selected container and its dependencies / dependents.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container: Main container configuration name.
        :type container: unicode | str
        :param instances: Instance names.
        :type instances: list or tuple
        :param kwargs: Additional keyword arguments to pass to the main container action.
        :return: Return values of created main containers.
        :rtype: list[(unicode | str, dict)]
        """
        dependency_path = self.get_dependency_path(map_name, container)
        for d in dependency_path:
            list(self.generate_actions(*d, c_flags=ACTION_DEPENDENCY_FLAG) or ())
        return super(AbstractDependentActionGenerator, self).get_all_actions(map_name, container, instances, **kwargs)


class AttachedPreparationMixin(object):
    """
    Utility mixin for preparing attached containers with file system owners and permissions.
    """
    prepare_local = True

    def _prepare_container(self, container_map, config_name, container_config, client_name, client_config, client, alias,
                           volume_container):
        """
        Runs a temporary container for preparing an attached volume for a container configuration.

        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param client: Client object.
        :type client: docker.client.Client
        :param alias: The alias name of the attached volume in the configuration.
        :type alias: unicode | str
        :param volume_container: The full name or id of the container sharing the volume.
        :type volume_container: unicode | str
        """
        include_host_config = use_host_config(client)
        apc_kwargs = self._policy.get_attached_preparation_create_kwargs(container_map, config_name, container_config,
                                                                         client_name, client_config, None, alias,
                                                                         volume_container,
                                                                         include_host_config=include_host_config)
        if not apc_kwargs:
            return
        images = self._policy.images[client_name]
        images.ensure_image(apc_kwargs['image'])
        client.wait(volume_container, timeout=client_config.get('wait_timeout'))
        temp_container = client.create_container(**apc_kwargs)
        temp_id = temp_container['Id']
        try:
            if include_host_config:
                aps_kwargs = dict(container=temp_id)
            else:
                aps_kwargs = self._policy.get_attached_preparation_host_config_kwargs(container_map, config_name,
                                                                                      container_config, client_name,
                                                                                      client_config, temp_id, alias,
                                                                                      volume_container)
            client.start(**aps_kwargs)
            client.wait(temp_id, timeout=client_config.get('wait_timeout'))
        finally:
            client.remove_container(temp_id)

    def prepare_container(self, container_map, config_name, container_config, client_name, client_config, client, alias,
                          volume_container):
        """
        Prepares an attached volume for a container configuration.

        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param client: Client object.
        :type client: docker.client.Client
        :param alias: The alias name of the attached volume in the configuration.
        :type alias: unicode | str
        :param volume_container: The full name or id of the container sharing the volume.
        :type volume_container: unicode | str
        """
        if not (self.prepare_local and hasattr(client, 'run_cmd')):
            return self._prepare_container(container_map, config_name, container_config, client_name, client_config,
                                           client, alias, volume_container)
        instance_detail = client.inspect_container(volume_container)
        volumes = get_instance_volumes(instance_detail)
        path = resolve_value(container_map.volumes[alias])
        local_path = volumes.get(path)
        if not local_path:
            raise ValueError("Could not locate local path of volume alias '{0}' / "
                             "path '{1}' in container {2}.".format(alias, path, volume_container))
        for cmd in get_preparation_cmd(container_config, local_path):
            client.run_cmd(cmd)


class ExecMixin(object):
    """
    Utility mixin for executing configured commands inside containers.
    """
    def exec_single_command(self, container_map, config_name, container_config, client_name, client_config, client,
                            container_name, instance_name, cmd, cmd_user):
        """
        Runs a single command inside a container.

        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param client: Client object.
        :type client: docker.client.Client
        :param container_name: Container to run the command in.
        :type container_name: unicode | str
        :param instance_name: Container instance name.
        :type instance_name: unicode | str
        :param cmd: Command to run.
        :type cmd: unicode | str | list[unicode | str]
        :param cmd_user: User to run the command as.
        :type cmd_user: unicode | str | int
        """
        log.debug("Creating exec command in container %s with user %s: %s.", container_name, cmd_user, cmd)
        ec_kwargs = self._policy.get_exec_create_kwargs(container_map, config_name, container_config, client_name,
                                                        client_config, container_name, instance_name, cmd, cmd_user)
        e_id = client.exec_create(**ec_kwargs)['Id']
        log.debug("Starting exec command with id %s.", e_id)
        es_kwargs = self._policy.get_exec_start_kwargs(container_map, config_name, container_config, client_name,
                                                       client_config, container_name, instance_name, e_id)
        client.exec_start(**es_kwargs)

    def exec_container_commands(self, container_map, config_name, container_config, client_name, client_config, client,
                                container_name, instance_name, is_initial):
        """
        Runs all configured commands of a container configuration inside the container instance.

        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param client: Client object.
        :type client: docker.client.Client
        :param container_name: Container to run the command in.
        :type container_name: unicode | str
        :param instance_name: Container instance name.
        :type instance_name: unicode | str
        :param is_initial: Set to ``True`` if the container has just been created or had never been started before.
        :type is_initial: bool
        """
        for cmd, cmd_user, cmd_policy in container_config.exec_commands:
            if cmd_policy != EXEC_POLICY_INITIAL or not is_initial:
                self.exec_single_command(container_map, config_name, container_config, client_name, client_config,
                                         client, container_name, instance_name, cmd, cmd_user)


class SignalMixin(object):
    def signal_stop(self, container_map, config_name, container_config, client_name, client_config, client,
                    container_name, instance_name, kwargs=None):
        """
        Stops a container, either using the default client stop method, or sending a custom signal and waiting
        for the container to stop.

        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param client: Client object.
        :type client: docker.client.Client
        :param container_name: Name of the container to stop.
        :type container_name: unicode | str
        :param instance_name: Container instance name.
        :type instance_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        sig = container_config.stop_signal
        stop_kwargs = self._policy.get_stop_kwargs(container_map, config_name, container_config, client_name,
                                                   client_config, container_name, instance_name, kwargs=kwargs)
        if not sig or sig == 'SIGTERM' or sig == signal.SIGTERM:
            client.stop(**stop_kwargs)
        else:
            log.debug("Sending signal %s to the container %s and waiting for stop.", sig, container_name)
            client.kill(container_name, signal=sig)
            client.wait(container_name, timeout=stop_kwargs.get('timeout', 10))


class ForwardActionGeneratorMixin(object):
    """
    Defines the dependency path as dependencies of a container configuration.
    """
    def get_dependency_path(self, map_name, config_name):
        return self._policy.get_dependencies(map_name, config_name)


class ReverseActionGeneratorMixin(object):
    """
    Defines the dependency path as dependents of a container configuration.
    """
    def get_dependency_path(self, map_name, config_name):
        return self._policy.get_dependents(map_name, config_name)
