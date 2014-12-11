# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod
import itertools

from ... import DEFAULT_COREIMAGE, DEFAULT_BASEIMAGE
from . import ACTION_DEPENDENCY_FLAG
from .dep import ContainerDependencyResolver
from .utils import extract_user, get_host_binds, init_options, update_kwargs


class BasePolicy(object):
    """
    Abstract base class providing the basic infrastructure for generating actions based on container state.

    Status detail and images are dictionaries of callables provided by the instantiating object. Their keys are the
    container map, and their values are functions which query the relevant client for the current status on demand.

    :param container_maps: Container maps.
    :type container_maps: dict[unicode, dockermap.map.container.ContainerMap]
    :param persistent_names: Names of persistent containers.
    :type persistent_names: list[unicode]
    :param status_detail: Dictionary of functions with argument container name.
    :type status_detail: dict
    :param images: Dictionary of functions with argument image name.
    :type images: dict
    """
    __metaclass__ = ABCMeta

    core_image = DEFAULT_COREIMAGE
    base_image = DEFAULT_BASEIMAGE

    def __init__(self, container_maps, persistent_names, status_detail, images):
        self._maps = container_maps
        self._persistent_names = set(persistent_names)
        self._status_detail = status_detail
        self._images = images
        self._status = {}
        self._f_resolver = ContainerDependencyResolver()
        for m in self._maps.values():
            self._f_resolver.update(m)
        self._r_resolver = ContainerDependencyResolver()
        for m in self._maps.values():
            self._r_resolver.update_backward(m)

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
    def get_create_kwargs(cls, container_map, config, default_image, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config: Container configuration object.
        :type config: dockermap.map.container.ContainerConfiguration
        :param default_image: Image name to use in case the container configuration does not specify.
        :type default_image: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            image=cls.iname(container_map, config.image or default_image),
            volumes=list(itertools.chain(config.shares,
                                         (container_map.volumes[b.volume] for b in config.binds))),
            user=extract_user(config.user),
        )
        update_kwargs(c_kwargs, init_options(config.create_options), kwargs)
        return c_kwargs

    @classmethod
    def get_attached_create_kwargs(cls, container_map, config, alias, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create an attached container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config: Container configuration object.
        :type config: dockermap.map.container.ContainerConfiguration
        :param alias: Alias name of the container volume.
        :type alias: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        path = container_map.volumes[alias]
        c_kwargs = dict(
            image=cls.base_image,
            volumes=[path],
            user=config.user,
        )
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_attached_prepare_kwargs(cls, container_map, config, alias, kwargs=None):
        """
        Generates keyword arguments for the Docker client to prepare an attached container (i.e. adjust user and
        permissions). The resulting dictionary should contain the following keys:

        * ``image``: The image name to use (in this implementation, :attr:`core_image`).
        * ``path``: The volume path to initialize.
        * ``user``: User to set as owner for the volume path.
        * ``permissions``: File system permissions to set for the volume path.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config: Container configuration object.
        :type config: dockermap.map.container.ContainerConfiguration
        :param alias: Alias name of the container volume.
        :type alias: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        path = container_map.volumes[alias]
        c_kwargs = dict(
            image=cls.core_image,
            path=path,
            user=config.user,
            permissions=config.permissions,
        )
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_start_kwargs(cls, container_map, config, instance, kwargs=None):
        """
        Generates keyword arguments for the Docker client to start a container.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config: Container configuration object.
        :type config: dockermap.map.container.ContainerConfiguration
        :param instance: Instance name.
        :type instance: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        map_name = container_map.name
        c_kwargs = dict(
            volumes_from=list(cls.cname(map_name, u_name) for u_name in itertools.chain(config.uses, config.attaches)),
            links=dict((cls.cname(map_name, l_name), alias) for l_name, alias in config.links),
            binds=get_host_binds(container_map, config, instance),
        )
        update_kwargs(c_kwargs, init_options(config.start_options), kwargs)
        return c_kwargs

    @classmethod
    def get_restart_kwargs(cls, container_map, config, instance, kwargs=None):
        """
        Generates keyword arguments for the Docker client to restart a container. In the base implementation always
        returns an empty dictionary, since there are no arguments the client would need.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config: Container configuration object.
        :type config: dockermap.map.container.ContainerConfiguration
        :param instance: Instance name.
        :type instance: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        return {}

    @classmethod
    def get_stop_kwargs(cls, container_map, config, instance, kwargs=None):
        """
        Generates keyword arguments for the Docker client to stop a container. In the base implementation always
        returns an empty dictionary, since there are no arguments the client would need.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config: Container configuration object.
        :type config: dockermap.map.container.ContainerConfiguration
        :param instance: Instance name.
        :type instance: unicode
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        return {}

    @classmethod
    def get_remove_kwargs(cls, container_map, config, kwargs=None):
        """
        Generates keyword arguments for the Docker client to remove a container. In the base implementation always
        returns an empty dictionary, since there are no arguments the client would need.

        :param container_map: Container map object.
        :type container_map: dockermap.map.container.ContainerMap
        :param config: Container configuration object.
        :type config: dockermap.map.container.ContainerConfiguration
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        return {}

    def get_container_status(self, map_name, container):
        """
        Retrieves the full current container configuration (using the ``inspect`` function) from the Docker service.

        :param map_name: Container map name.
        :type map_name: unicode
        :param container: Container name.
        :type container: unicode
        :return: Container information.
        :rtype: dict
        """
        return self._status_detail[map_name](container)

    def get_image_id(self, map_name, image_name):
        """
        Retrieves the image id of the given image name. In fact this will fetch all image names from the affected client
        on the first request and cache all names for later use.

        :param map_name: Container map name.
        :type map_name: unicode
        :param image_name: Image name.
        :type image_name: unicode
        :param: Image id.
        :rtype: unicode
        """
        return self._images[map_name](image_name)

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
    def status(self):
        """
        Container status to base actions on.

        :return: Dictionary of container states.
        :rtype: dict[unicode, int]
        """
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def persistent_names(self):
        """
        Names of persistent containers of the container configurations.

        :return: Set of container names.
        :rtype: set[unicode]
        """
        return self._persistent_names

    @property
    def status_detail(self):
        """
        Status detail functions on containers.

        :return: Dictionary of functions to retrieve container status details.
        :rtype: dict[unicode, function]
        """
        return self._status_detail

    @property
    def images(self):
        """
        Image information functions.

        :return: Dictionary of functions to retrieve image names.
        :rtype: dict[unicode, function]
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
        :param c_map: Container map instance.
        :param container_name: Container configuration name.
        :param c_config: Container configuration object.
        :param instances: Instance names as a list. Can be ``[None]``
        :param flags: Flags for the current container, as defined in :module:`dockermap.map.policy.actions`.
        :param args: Additional positional arguments.
        :param kwargs: Additional keyword arguments.
        :return: An iterable of container actions. Can be a generator.
        :rtype: dockermap.map.policy.actions.ContainerAction
        """
        pass

    def get_actions(self, map_name, container, instances=None, **kwargs):
        """
        Generates actions for the selected container and its dependencies / dependents.

        :param map_name: Container map name.
        :type map_name: unicode
        :param container: Main container configuration name.
        :type container: unicode
        :param instances: Instance names.
        :type instances: list or tuple
        :param kwargs: Additional keyword arguments to pass to the main container action.
        :return: A generator of container actions.
        :rtype: list[dockermap.map.policy.actions.ContainerAction]
        """
        def _gen_actions(c_map_name, c_container, c_instance, c_flags=0, **c_kwargs):
            c_map = self._policy.container_maps[c_map_name]
            c_config = c_map.get_existing(c_container)
            c_instances = [c_instance] if c_instance else c_config.instances or [None]
            return self.generate_item_actions(map_name, c_map, c_container, c_config, c_instances, c_flags, **c_kwargs)

        dependency_path = self.get_dependency_path(map_name, container)
        dep_actions = itertools.chain.from_iterable(_gen_actions(*d, c_flags=ACTION_DEPENDENCY_FLAG)
                                                    for d in dependency_path)
        return itertools.chain(dep_actions, _gen_actions(map_name, container, instances, c_flags=0, **kwargs))

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
