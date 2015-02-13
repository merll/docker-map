# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod
import itertools

from ... import DEFAULT_COREIMAGE, DEFAULT_BASEIMAGE
from ...shortcuts import get_user_group, str_arg
from . import ACTION_DEPENDENCY_FLAG
from .dep import ContainerDependencyResolver
from .cache import ContainerCache, ImageCache
from .utils import extract_user, get_host_binds, get_port_bindings, init_options, update_kwargs


class BasePolicy(object):
    """
    Abstract base class providing the basic infrastructure for generating actions based on container state.

    :param container_maps: Container maps.
    :type container_maps: dict[unicode, dockermap.map.container.ContainerMap]
    :param clients: Dictionary of clients.
    :type clients: dict[unicode, dockermap.map.config.ClientConfiguration]
    """
    __metaclass__ = ABCMeta

    core_image = DEFAULT_COREIMAGE
    base_image = DEFAULT_BASEIMAGE

    def __init__(self, container_maps, clients):
        self._maps = container_maps
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instance: Instance name (optional).
        :type instance: unicode
        :return: Container name.
        :rtype: unicode
        """
        if instance:
            return '.'.join((map_name, container, instance))
        return '.'.join((map_name, container))

    @classmethod
    def resolve_cname(cls, container_name, includes_map=True):
        """
        The reverse function of :meth:`cname` for resolving a container name into map name, container configuration,
        and instance name. The instance name may be ``None`` if not present. In case the map name is not present
        in the container name, ``includes_map`` should be set to ``False`` for only resolving configuration name and map
        name.

        :param container_name: Container name.
        :type container_name: unicode
        :param includes_map: Whether the name includes a map name (e.g. for running containers) or not (e.g. for
         references within the same map).
        :return: Tuple of container map name (optional), container configuration name, and instance.
        :rtype: tuple[unicode]
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
        :type image: unicode.
        :return: Image name, where applicable prefixed with a repository.
        :rtype: unicode
        """
        if '/' in image:
            if image[0] == '/':
                return image[1:]
            return image
        repository = container_map.repository
        if repository:
            return '/'.join((repository, image))
        return image

    @classmethod
    def get_hostname(cls, client_name, container_name):
        """
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param container_name: Container name.
        :type container_name: unicode
        """
        return '-'.join((container_name, client_name))

    @classmethod
    def get_domainname(cls, container_map, container_config, client_config):
        """
        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        """
        return client_config.get('domainname', container_map.default_domain)

    @classmethod
    def get_create_kwargs(cls, container_map, container_config, client_name, client_config, container_name,
                          default_image, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name.
        :type container_name: unicode
        :param default_image: Image name to use in case the container configuration does not specify.
        :type default_image: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            name=container_name,
            image=cls.iname(container_map, container_config.image or default_image),
            volumes=list(itertools.chain(container_config.shares,
                                         (container_map.volumes[b.volume] for b in container_config.binds))),
            user=extract_user(container_config.user),
            ports=[port_binding.exposed_port
                   for port_binding in container_config.exposes if port_binding.exposed_port],
            hostname=cls.get_hostname(client_name, container_name) if container_map.set_hostname else None,
            domainname=cls.get_domainname(container_map, container_config, client_config),
        )
        update_kwargs(c_kwargs, init_options(container_config.create_options), kwargs)
        return c_kwargs

    @classmethod
    def get_attached_create_kwargs(cls, container_map, container_config, client_name, client_config, container_name,
                                   alias, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create an attached container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container_name: Container name.
        :type container_name: unicode
        :param alias: Alias name of the container volume.
        :type alias: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        path = container_map.volumes[alias]
        c_kwargs = dict(
            name=container_name,
            image=cls.base_image,
            volumes=[path],
            user=container_config.user,
        )
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_start_kwargs(cls, container_map, container_config, client_name, client_config, container, instance,
                         kwargs=None):
        """
        Generates keyword arguments for the Docker client to start a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container: Container name or id.
        :type container: unicode
        :param instance: Instance name.
        :type instance: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        map_name = container_map.name
        c_kwargs = dict(
            container=container,
            links=dict((cls.cname(map_name, l_name), alias) for l_name, alias in container_config.links),
            binds=get_host_binds(container_map, container_config, instance),
            volumes_from=list(cls.cname(map_name, u_name)
                              for u_name in itertools.chain(container_config.uses, container_config.attaches)),
            port_bindings=get_port_bindings(container_config, client_config),
        )
        update_kwargs(c_kwargs, init_options(container_config.start_options), kwargs)
        return c_kwargs

    @classmethod
    def get_attached_preparation_create_kwargs(cls, container_map, container_config, client_name, client_config, alias,
                                               volume_container, kwargs=None):
        """
        Generates keyword arguments for the Docker client to prepare an attached container (i.e. adjust user and
        permissions).

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param alias: Alias name of the container volume.
        :type alias: unicode
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        def _get_cmd():
            user = container_config.user
            if user:
                yield ' '.join(('chown -R', get_user_group(user), str_arg(path)))
            permissions = container_config.permissions
            if container_config.permissions:
                yield ' '.join(('chmod -R', permissions, str_arg(path)))

        path = container_map.volumes[alias]
        c_kwargs = dict(
            image=cls.core_image,
            command=' && '.join(_get_cmd()),
            user='root',
        )
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_attached_start_kwargs(cls, container_map, container_config, client_name, client_config, container, alias,
                                  kwargs=None):
        """
        Generates keyword arguments for the Docker client to start an attached container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container: Container name or id.
        :type container: unicode
        :param alias: Alias name of the container volume.
        :type alias: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(container=container)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_attached_preparation_start_kwargs(cls, container_map, container_config, client_name, client_config,
                                              container, alias, volume_container, kwargs=None):
        """
        Generates keyword arguments for the Docker client to prepare an attached container (i.e. adjust user and
        permissions).

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container: Container name or id.
        :type container: unicode
        :param alias: Alias name of the container volume.
        :type alias: unicode
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            container=container,
            volumes_from=[volume_container],
        )
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_restart_kwargs(cls, container_map, container_config, client_name, client_config, container, instance,
                           kwargs=None):
        """
        Generates keyword arguments for the Docker client to restart a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container: Container name or id.
        :type container: unicode
        :param instance: Instance name.
        :type instance: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(container=container)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_stop_kwargs(cls, container_map, container_config, client_name, client_config, container, instance,
                        kwargs=None):
        """
        Generates keyword arguments for the Docker client to stop a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container: Container name or id.
        :type container: unicode
        :param instance: Instance name.
        :type instance: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            container=container,
            timeout=client_config.get('stop_timeout', 10)
        )
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_remove_kwargs(cls, container_map, container_config, client_name, client_config, container, kwargs=None):
        """
        Generates keyword arguments for the Docker client to remove a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param container: Container name or id.
        :type container: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(container=container)
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
        :rtype: tuple[tuple[unicode, docker.client.Client, dockermap.map.config.ClientConfiguration]]
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :return: Dependency container map names, container configuration names, and instances.
        :rtype: iterator[tuple(unicode, unicode, unicode)]
        """
        return reversed(self._f_resolver.get_container_dependencies(map_name, container))

    def get_dependents(self, map_name, container):
        """
        Generates the list of dependent containers, in reverse order (i.e. the last dependent coming first).

        :param map_name: Container map name.
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :return: Dependent container map names, container configuration names, and instances.
        :rtype: iterator[tuple(unicode, unicode, unicode)]
        """
        return reversed(self._r_resolver.get_container_dependencies(map_name, container))

    @abstractmethod
    def create_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for the ``create`` command, which may involve any container action (create, start, stop,
        remove) as necessary. To be implemented by subclasses.

        :param map_name: Container map name.
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list or tuple or unicode
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list or tuple or unicode
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list or tuple or unicode
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list or tuple or unicode
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list or tuple or unicode
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list or tuple or unicode
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list or tuple or unicode
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
        :type map_name: unicode
        :param container: Container configuration name.
        :type container: unicode
        :param instances: Instance names. Should accept a single string, a list or tuple, or ``None``.
        :type instances: list or tuple or unicode
        :param kwargs: Additional keyword arguments to pass.
        :return: Generator for container actions.
        :rtype: generator[dockermap.map.policy.action.ContainerAction]
        """
        raise NotImplementedError("This policy does not support the update command.")

    @property
    def container_maps(self):
        """
        Container maps with container configurations to base actions on.

        :return: Dictionary of container maps.
        :rtype: dict[unicode, dockermap.map.container.ContainerMap]
        """
        return self._maps

    @property
    def clients(self):
        """
        Docker client objects and configurations.

        :return: Dictionary of Docker client objects.
        :rtype: dict[unicode, dockermap.map.config.ClientConfiguration]
        """
        return self._clients

    @property
    def container_names(self):
        """
        Names of existing containers on each map.

        :return: Dictionary of container names.
        :rtype: dict[unicode, dockermap.map.policy.cache.CachedContainerNames]
        """
        return self._container_names

    @property
    def images(self):
        """
        Image information functions.

        :return: Dictionary of image names per client.
        :rtype: dict[unicode, dockermap.map.policy.cache.CachedImages]
        """
        return self._images


class AbstractActionGenerator(object):
    """
    Abstract base implementation for an action generator, which generates actions for a policy.

    :param policy: Policy object instance.
    :type policy: BasePolicy
    """
    __metaclass__ = ABCMeta

    def __init__(self, policy=None):
        self._policy = policy

    @abstractmethod
    def get_dependency_path(self, map_name, container_name):
        """
        To be implemented by subclasses (or using :class:`ForwardActionGeneratorMixin` or
        class:`ReverseActionGeneratorMixin`). Should provide an iterable of objects to be handled before the explicitly
        selected container configuration.

        :param map_name: Container map name.
        :param container_name: Container configuration name.
        :return: Iterable of dependency objects in tuples of map name, container (config) name, instance.
        :rtype: list[tuple]
        """
        pass

    @abstractmethod
    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        """
        To be implemented by subclasses. Should generate the actions on a single item, which can be either a dependency
        or a explicitly selected container.

        :param map_name: Container map name.
        :type map_name: unicode
        :param c_map: Container map instance.
        :type c_map: dockermap.map.container.ContainerMap
        :param container_name: Container configuration name.
        :type container_name: unicode
        :param c_config: Container configuration object.
        :type c_config: dockermap.map.config.ContainerConfiguration
        :param instances: Instance names as a list. Can be ``[None]``
        :type instances: list[unicode]
        :param flags: Flags for the current container, as defined in :mod:`~dockermap.map.policy.actions`.
        :type flags: int
        :param args: Additional positional arguments.
        :param kwargs: Additional keyword arguments.
        """
        pass

    def get_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates and performs actions for the selected container and its dependencies / dependents.

        :param map_name: Container map name.
        :type map_name: unicode
        :param container: Main container configuration name.
        :type container: unicode
        :param instances: Instance names.
        :type instances: list or tuple
        :param kwargs: Additional keyword arguments to pass to the main container action.
        :return: Return values of created main containers.
        :rtype: list[(unicode, dict)]
        """
        def _gen_actions(c_map_name, c_container, c_instance, c_flags=0, **c_kwargs):
            c_map = self._policy.container_maps[c_map_name]
            c_config = c_map.get_existing(c_container)
            c_instances = [c_instance] if c_instance else c_config.instances or [None]
            return self.generate_item_actions(map_name, c_map, c_container, c_config, c_instances, c_flags, **c_kwargs)

        dependency_path = self.get_dependency_path(map_name, container)
        for d in dependency_path:
            list(_gen_actions(*d, c_flags=ACTION_DEPENDENCY_FLAG) or ())
        return list(_gen_actions(map_name, container, instances, c_flags=0, **kwargs) or ())

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


class AttachedPreparationMixin(object):
    """
    Utility mixin for preparing attached containers with file system owners and permissions.
    """
    def prepare_container(self, images, client, container_map, container_config, client_name, client_config, alias,
                          volume_container):
        """
        Runs a temporary container for preparing an attached volume for a container configuration.

        :param images: Cached image names.
        :type images: dockermap.map.policy.cache.CachedImageSet
        :param client: Client object.
        :type client: docker.client.Client
        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client configuration name.
        :type client_name: unicode
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param alias: The alias name of the attached volume in the configuration.
        :type alias: unicode
        :param volume_container: The full name or id of the container sharing the volume.
        :type volume_container: unicode
        """
        client.wait(volume_container, timeout=client_config.get('wait_timeout'))
        apc_kwargs = self._policy.get_attached_preparation_create_kwargs(container_map, container_config, client_name,
                                                                         client_config, alias, volume_container)
        images.ensure_image(apc_kwargs['image'])
        temp_container = client.create_container(**apc_kwargs)
        temp_id = temp_container['Id']
        try:
            aps_kwargs = self._policy.get_attached_preparation_start_kwargs(container_map, container_config,
                                                                            client_name, client_config, temp_id, alias,
                                                                            volume_container)
            client.start(**aps_kwargs)
            client.wait(temp_id, timeout=client_config.get('wait_timeout'))
        finally:
            client.remove_container(temp_id)


class ForwardActionGeneratorMixin(object):
    """
    Defines the dependency path as dependencies of a container configuration.
    """
    def get_dependency_path(self, map_name, container_name):
        return self._policy.get_dependencies(map_name, container_name)


class ReverseActionGeneratorMixin(object):
    """
    Defines the dependency path as dependents of a container configuration.
    """
    def get_dependency_path(self, map_name, container_name):
        return self._policy.get_dependents(map_name, container_name)
