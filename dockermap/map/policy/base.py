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
    :param container_maps: Container maps.
    :type container_maps: dict[unicode, dockermap.map.container.ContainerMap]
    :param persistent_names: Names of persistent containers.
    :type persistent_names: list[unicode]
    :param status_detail: Dictionary of functions with argument container name.
    :type status_detail: dict
    :param images: Dictionary of functions with argument image name
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
        if instance:
            return '.'.join((map_name, container, instance))
        return '.'.join((map_name, container))

    @classmethod
    def iname(cls, container_map, image):
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
        return {}

    @classmethod
    def get_stop_kwargs(cls, container_map, config, instance, kwargs=None):
        return {}

    @classmethod
    def get_remove_kwargs(cls, container_map, config, kwargs=None):
        return {}

    def get_container_status(self, map_name, container):
        return self._status_detail[map_name](container)

    def get_image_id(self, map_name, image_name):
        return self._images[map_name](image_name)

    def get_dependencies(self, map_name, container):
        return reversed(self._f_resolver.get_container_dependencies(map_name, container))

    def get_dependents(self, map_name, container):
        return reversed(self._r_resolver.get_container_dependencies(map_name, container))

    @abstractmethod
    def create_actions(self, map_name, container, instances=None, **kwargs):
        pass

    @abstractmethod
    def start_actions(self, map_name, container, instances=None, **kwargs):
        pass

    @abstractmethod
    def stop_actions(self, map_name, container, instances=None, **kwargs):
        pass

    @abstractmethod
    def remove_actions(self, map_name, container, instances=None, **kwargs):
        pass

    def startup_actions(self, map_name, container, instances=None, **kwargs):
        raise NotImplementedError("This policy does not support the startup command.")

    def shutdown_actions(self, map_name, container, instances=None, **kwargs):
        raise NotImplementedError("This policy does not support the shutdown command.")

    def restart_actions(self, map_name, container, instances=None, **kwargs):
        raise NotImplementedError("This policy does not support the restart command.")

    def update_actions(self, map_name, container, instances=None, **kwargs):
        raise NotImplementedError("This policy does not support the update command.")

    @property
    def container_maps(self):
        return self._maps

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def persistent_names(self):
        return self._persistent_names

    @property
    def status_detail(self):
        return self._status_detail

    @property
    def images(self):
        return self._images


class AbstractActionGenerator(object):
    """
    :type policy: BasePolicy
    """
    __metaclass__ = ABCMeta

    def __init__(self, policy=None):
        self._policy = policy

    @abstractmethod
    def get_dependency_path(self, map_name, container_name):
        pass

    @abstractmethod
    def generate_item_actions(self, map_name, c_map, container_name, c_config, instances, flags, *args, **kwargs):
        pass

    def get_actions(self, map_name, container, instances=None, **kwargs):
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
        return self._policy

    @policy.setter
    def policy(self, value):
        self._policy = value


class ForwardActionGeneratorMixin(object):
    def get_dependency_path(self, map_name, container_name):
        return self._policy.get_dependencies(map_name, container_name)


class ReverseActionGeneratorMixin(object):
    def get_dependency_path(self, map_name, container_name):
        return self._policy.get_dependents(map_name, container_name)
