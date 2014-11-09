# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
import six

from docker.errors import APIError

from .. import DEFAULT_BASEIMAGE, DEFAULT_COREIMAGE
from ..shortcuts import get_user_group
from .container import ContainerDependencyResolver


def _extract_user(user):
    if not user and user != 0 and user != '0':
        return None
    if isinstance(user, tuple):
        return user[0]
    if isinstance(user, int):
        return six.text_type(user)
    return user.partition(':')[0]


def _update_kwargs(kwargs, *updates):
    for update in updates:
        for key, u_item in six.iteritems(update):
            if not u_item:
                continue
            kw_item = kwargs.get(key)
            if isinstance(u_item, (tuple, list)):
                if kw_item:
                    kw_item.extend(u_item)
                else:
                    kwargs[key] = u_item[:]
            elif isinstance(u_item, dict):
                if kw_item:
                    kw_item.update(u_item)
                else:
                    kwargs[key] = u_item.copy()
            else:
                kwargs[key] = u_item


def _init_options(options):
    if options:
        if callable(options):
            return options()
        return options
    return {}


class MappingDockerClient(object):
    """
    Reflects a :class:`~dockermap.map.container.ContainerMap` instance on a Docker client
    (:class:`~dockermap.map.base.DockerClientWrapper`).
    This means that the usual actions of creating containers, starting containers, and stopping containers consider
    dependent containers and volume assignments.

    Image names and container names are cached. In order to force a refresh, use :meth:`refresh_names`.

    :param container_map: :class:`~dockermap.map.container.ContainerMap` instance.
    :type container_map: dockermap.map.container.ContainerMap
    :param docker_client: :class:`~dockermap.map.base.DockerClientWrapper` instance.
    :type docker_client: dockermap.map.base.DockerClientWrapper
    """
    def __init__(self, container_map=None, docker_client=None):
        self._map = container_map
        self._client = docker_client
        self._container_names = None
        self._image_tags = None

    def _get(self, container):
        config = self._map.get_existing(container)
        if not config:
            raise ValueError("No configurations found for container '{0}'.".format(container))
        return config

    def _cname(self, container, instance=None):
        return self._map.cname(container, instance)

    def _iname(self, image):
        return self._map.iname(image)

    def _check_refresh_containers(self, force=False):
        if force or self._container_names is None:
            self._container_names = self._client.get_container_names()

    def _check_refresh_images(self, force=False):
        if force or self._image_tags is None:
            self._image_tags = self._client.get_image_tags()

    def _get_container_names(self):
        self._check_refresh_containers()
        return self._container_names

    def _get_image_tags(self):
        self._check_refresh_images()
        return self._image_tags

    def _ensure_images(self, *images):
        def _check_image(image_name):
            image_name, __, tag = image_name.partition(':')
            if tag:
                full_name = image_name
            else:
                full_name = ':'.join((image_name, 'latest'))
            if full_name not in self._get_image_tags():
                self._client.import_image(image=image_name, tag=tag or 'latest')
                return True
            return False

        new_images = [_check_image(image) for image in images]
        if any(new_images):
            self._check_refresh_images(True)

    def _create_named_container(self, image, name, **kwargs):
        container = self._client.create_container(image, name, **kwargs)
        self._container_names.add(name)
        return container

    def _remove_container(self, name, **kwargs):
        self._container_names.remove(name)
        self._client.remove_container(name, **kwargs)

    def _run_and_dispose(self, coreimage, entrypoint, command, user, volumes_from):
        tmp_container = self._client.create_container(coreimage, entrypoint=entrypoint, command=command, user=user)['Id']
        try:
            self._client.start(tmp_container, volumes_from=volumes_from)
            self._client.wait(tmp_container)
            self._client.push_container_logs(tmp_container)
        finally:
            self._client.remove_container(tmp_container)

    def _adjust_permissions(self, coreimage, container_name, path, user, permissions):
        if not user and not permissions:
            return
        if user:
            self._client.push_log("Adjusting user for container '{0}' to '{1}'.".format(container_name, user))
            self._run_and_dispose(coreimage, None, ['chown', '-R', get_user_group(user), path], 'root', [container_name])
        if permissions:
            self._client.push_log("Adjusting permissions for container '{0}' to '{1}'.".format(container_name, permissions))
            self._run_and_dispose(coreimage, None, ['chmod', '-R', permissions, path], 'root', [container_name])

    def _get_or_create_volume(self, baseimage, coreimage, alias, user, permissions):
        c_name = self._cname(alias)
        if c_name not in self._get_container_names():
            path = self._get_volume_path(alias)
            self._create_named_container(baseimage, c_name, volumes=[path], user=user)
            self._client.start(c_name)
            self._client.wait(c_name)
            self._adjust_permissions(coreimage, c_name, path, user, permissions)
        else:
            self._client.push_log("Container '{0}' exists.".format(c_name))
        return alias, c_name

    def _get_volume_path(self, alias):
        path = self._map.volumes.get(alias)
        if not path:
            raise ValueError("No path found for volume '{0}'.".format(alias))
        return path

    def _get_instance_containers(self, container, instances=None, **kwargs):
        config = self._get(container)
        c_instances = instances or config.instances or [None]
        image = self._iname(config.image or container)
        c_kwargs = {
            'volumes': list(itertools.chain(config.shares,
                                            (self._get_volume_path(b.volume) for b in config.binds))),
            'user': _extract_user(config.user),
        }
        _update_kwargs(c_kwargs, _init_options(config.create_options), kwargs)

        self._ensure_images(image)
        for i in c_instances:
            c_name = self._cname(container, i)
            if c_name not in self._get_container_names():
                self._create_named_container(image, c_name, **c_kwargs)
            else:
                self._client.push_log("Container '{0}' exists.".format(c_name))
            yield container, c_name

    def _start_instance_containers(self, container, instances=None, **kwargs):
        def _get_host_binds(instance):
            for alias, readonly in config.binds:
                share = self._map.host.get(alias, instance)
                if share:
                    bind = {'bind': self._get_volume_path(alias), 'ro': readonly}
                    yield share, bind

        config = self._get(container)
        c_instances = instances or config.instances or [None]
        c_kwargs = {
            'volumes_from': list(map(self._cname, itertools.chain(config.uses, config.attaches))),
            'links': dict((self._cname(name), alias) for name, alias in config.links),
        }
        c_options = _init_options(config.start_options)

        for i in c_instances:
            c_name = self._cname(container, i)
            ic_kwargs = c_kwargs.copy()
            _update_kwargs(ic_kwargs, {'binds': dict(_get_host_binds(i))}, c_options, kwargs)
            self._client.start(c_name, **ic_kwargs)

    def _stop_instance_containers(self, container, instances=None, **kwargs):
        c_instances = instances or self._get(container).instances or [None]
        for i in c_instances:
            c_name = self._cname(container, i)
            if c_name in self._get_container_names():
                try:
                    self._client.stop(c_name, **kwargs)
                except APIError as e:
                    if e.response.status_code != 404:
                        self._client.push_log("Failed to stop container '{0}': {1}".format(c_name, e.explanation))

    def _remove_instance_containers(self, container, instances=None, **kwargs):
        c_instances = instances or self._get(container).instances or [None]
        for i in c_instances:
            c_name = self._cname(container, i)
            if c_name in self._get_container_names():
                try:
                    self._client.remove_container(c_name, **kwargs)
                except APIError as e:
                    self._client.push_log("Failed to remove container '{0}': ".format(c_name, e.explanation))

    def _container_dependencies(self, container):
        return reversed(ContainerDependencyResolver(self._map).get_dependencies(container))

    def _container_dependents(self, container):
        resolver = ContainerDependencyResolver()
        resolver.update_backward(self._map)
        return reversed(resolver.get_dependencies(container))

    def create_attached_volumes(self, container, baseimage=DEFAULT_BASEIMAGE, coreimage=DEFAULT_COREIMAGE):
        """
        Creates attached volumes for a container configuration; that means that a minimal container image will
        be created for the purpose of sharing the volumes as set in the `attaches` property. Multiple instances share
        the same attached container.

        :param container: Container name.
        :param baseimage: Base image to use for sharing the volume. Default is :const:`DEFAULT_BASEIMAGE`.
        :param coreimage: Image with coreutils to initialize the containers. Default is :const:`DEFAULT_COREIMAGE`.
        :return: A dictionary with container aliases, mapping them to names of the instantiated Docker container.
        :rtype: dict
        """
        config = self._get(container)
        self._ensure_images(baseimage, coreimage)
        return dict(self._get_or_create_volume(baseimage, coreimage, a, config.user, config.permissions)
                    for a in config.attaches)

    def create(self, container, instances=None, create_dependencies=True, create_attached=True,
               attached_baseimage=DEFAULT_BASEIMAGE, **kwargs):
        """
        Creates container instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance name to create. If not specified, will create all instances as specified in the
         configuration (or just one default instance).
        :type instances: tuple or list
        :param create_dependencies: Resolve and create dependency containers.
        :type create_dependencies: bool
        :param create_attached: Create attached volumes (also applies to all dependencies, if applicable).
        :type create_attached: bool
        :param attached_baseimage: Base image for creating attached volumes.
        :type attached_baseimage: unicode
        :param kwargs: Additional kwargs for creating the container. `volumes` and `environment` enhance the generated
         arguments; `user` overrides the user from the container configuration.
        :return: List of tuples with container aliases and names of container instances. Does not include attached
         containers.
        """
        def _create_containers(c_name, c_instances=None, c_kwargs={}):
            if create_attached:
                self.create_attached_volumes(c_name, attached_baseimage)
            return tuple(self._get_instance_containers(c_name, c_instances, **c_kwargs))

        if create_dependencies:
            created_containers = list(map(_create_containers, self._container_dependencies(container)))
            created_containers.append(_create_containers(container, instances, kwargs))
            return list(itertools.chain.from_iterable(created_containers))
        return _create_containers(container, instances, kwargs)

    def start(self, container, instances=None, start_dependencies=True, **kwargs):
        """
        Starts instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to start. If not specified, will start all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param start_dependencies: Resolve and start dependency containers.
        :type start_dependencies: bool
        :param kwargs: Additional kwargs for starting the container. `binds` and `volumes_from` will enhance the
         generated arguments.
        """
        if start_dependencies:
            for dependent_container in self._container_dependencies(container):
                self._start_instance_containers(dependent_container)

        self._start_instance_containers(container, instances, **kwargs)

    def stop(self, container, instances=None, stop_dependent=True, **kwargs):
        """
        Stops instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to stop. If not specified, will stop all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param stop_dependent: Resolve and stop dependent containers.
        :type stop_dependent: bool
        :param kwargs: Additional kwargs for stopping the container and its dependents.
        """
        if stop_dependent:
            for dependent_container in self._container_dependents(container):
                self._stop_instance_containers(dependent_container, **kwargs)

        self._stop_instance_containers(container, instances, **kwargs)

    def remove(self, container, instances=None, remove_dependent=True, **kwargs):
        """
        Remove instances from a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param remove_dependent: Resolve and remove dependent containers.
        :type remove_dependent: bool
        :param kwargs: Additional kwargs for removing the container and its dependents.
        """
        if remove_dependent:
            for dependent_container in self._container_dependents(container):
                self._remove_instance_containers(dependent_container, **kwargs)

        self._remove_instance_containers(container, instances, **kwargs)

    def wait(self, container, instance=None, log=True):
        """
        Wait for a container.

        :param container: Container name.
        :type container: unicode
        :param instance: Instance name to remove. If not specified, removes the default instance.
        :type instance: unicode
        :param log: Log the container output before removing it.
        :type log: bool
        """
        c_name = self._cname(container, instance)
        self._client.wait(c_name)
        if log:
            self._client.push_container_logs(c_name)

    def wait_and_remove(self, container, instance=None, log=True):
        """
        Wait for, and then remove a container.

        :param container: Container name.
        :type container: unicode
        :param instance: Instance name to remove. If not specified, removes the default instance.
        :type instance: unicode
        :param log: Log the container output before removing it.
        :type log: bool
        """
        self.wait(container, instance, log)
        self.remove(container, [instance])

    def refresh_names(self):
        """
        Refresh the container name cache.
        """
        self._check_refresh_images(True)
        self._check_refresh_containers(True)

    @property
    def client(self):
        """
        Docker client.

        :return: :class:`.base.DockerClientWrapper` instance.
        :rtype: dockermap.map.base.DockerClientWrapper
        """
        return self._client

    @client.setter
    def client(self, value):
        self._client = value
        self._container_names = None
        self._image_tags = None

    @property
    def map(self):
        """
        Container map.

        :return: :class:`.container.ContainerMap` instance.
        :rtype: dockermap.map.container.ContainerMap
        """
        return self._map

    @map.setter
    def map(self, value):
        self._map = value
