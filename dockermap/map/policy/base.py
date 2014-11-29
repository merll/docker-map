# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod
import itertools

from ... import DEFAULT_COREIMAGE, DEFAULT_BASEIMAGE
from . import ACTION_DEPENDENCY_FLAG
from .dep import ContainerDependencyResolver
from .utils import extract_user, get_host_binds, get_volume_path, init_options, update_kwargs, get_config


class BasePolicy(object):
    """
    :param container_maps: Container maps.
    :type container_maps: dict[unicode, dockermap.map.container.ContainerMap]
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
                                         (get_volume_path(container_map, b.volume) for b in config.binds))),
            user=extract_user(config.user),
        )
        update_kwargs(c_kwargs, init_options(config.create_options), kwargs)
        return c_kwargs

    @classmethod
    def get_attached_create_kwargs(cls, container_map, config, alias, kwargs=None):
        path = get_volume_path(container_map, alias)
        c_kwargs = dict(
            image=cls.base_image,
            volumes=[path],
            user=config.user,
        )
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    @classmethod
    def get_attached_prepare_kwargs(cls, container_map, config, alias, kwargs=None):
        path = get_volume_path(container_map, alias)
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
            binds=dict(get_host_binds(container_map, config, instance))
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


class BaseActionMixin(object):
    def get_base_actions(self, action_generator, map_name, container, instances=None, **kwargs):
        def _dep_actions(d_map_name, d_container, d_instance):
            d_map = self._maps[d_map_name]
            d_config = get_config(d_map, d_container)
            d_instances = [d_instance] if d_instance else d_config.instances or [None]
            return action_generator(map_name, d_map, d_container, d_config, d_instances, ACTION_DEPENDENCY_FLAG)

        dependencies = self.get_dependencies(map_name, container)
        dep_actions = itertools.chain.from_iterable(_dep_actions(*d) for d in dependencies)
        c_map = self._maps[map_name]
        c_config = get_config(c_map, container)
        c_instances = instances or c_config.instances or [None]
        return itertools.chain(dep_actions, action_generator(map_name, c_map, container, c_config, c_instances, **kwargs))
