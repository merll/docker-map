# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
import six

from docker.errors import APIError

from .. import DEFAULT_BASEIMAGE, DEFAULT_COREIMAGE
from ..shortcuts import get_user_group
from .container import ContainerDependencyResolver


def _extract_user(user):
    if user is None or user == '':
        return None
    if isinstance(user, tuple):
        return user[0]
    if isinstance(user, int):
        return six.text_type(user)
    return user.partition(':')[0]


class MappingDockerClient(object):
    """
    Reflects a :class:`.volumes.ContainerMap` instance on a Docker client (:class:`.client.DockerClientWrapper`).
    This means that the usual actions of creating containers, starting containers, and stopping containers consider
    dependent containers and volume assignments.

    Image names and container names are cached. In order to force a refresh, use :func:`refresh_names`.

    :param container_map: :class:`.container.ContainerMap` instance.
    :type container_map: dockermap.map.container.ContainerMap
    :param docker_client: :class:`.base.DockerClientWrapper` instance.
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
        def _check_image(image):
            image, __, tag = image.partition(':')
            if tag:
                i_name = image
            else:
                i_name = ':'.join((image, 'latest'))
            if i_name not in self._get_image_tags():
                self._client.import_image(image=image, tag=tag or 'latest')
                return True
            return False

        new_images = [_check_image(image) for image in images]
        if any(new_images):
            self._check_refresh_images(True)

    def _create_named_container(self, image, name, **kwargs):
        container = self._client.create_container(image, name, **kwargs)
        self._container_names.add(name)
        return container

    def _remove_container(self, name):
        self._container_names.remove(name)
        self._client.remove_container(name)

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

    def _get_instance_containers(self, container, instances=None, volumes=None, user=None, **kwargs):
        config = self._get(container)
        c_instances = instances or config.instances or [None]
        image = self._iname(config.image or container)
        shared_volumes = list(itertools.chain(volumes or [], config.shares,
                                              (self._get_volume_path(b.volume) for b in config.binds))) or None
        if config.create_options:
            if callable(config.create_options):
                c_kwargs = config.create_options()
            else:
                c_kwargs = config.create_options.copy()
            c_user = user or c_kwargs.pop('user', _extract_user(config.user))
            c_kwargs.update(kwargs)
        else:
            c_user = user or _extract_user(config.user)
            c_kwargs = kwargs

        self._ensure_images(image)
        for i in c_instances:
            c_name = self._cname(container, i)
            if c_name not in self._get_container_names():
                self._create_named_container(image, c_name, volumes=shared_volumes, user=c_user, **c_kwargs)
                self._container_names.add(c_name)
            else:
                self._client.push_log("Container '{0}' exists.".format(c_name))
            yield container, c_name

    def _start_instance_containers(self, container, instances=None, binds=None, volumes_from=None, links=None, **kwargs):
        def _get_host_binds(instance):
            for alias, readonly in config.binds:
                share = self._map.host.get(alias, instance)
                if share:
                    bind = {'bind': self._get_volume_path(alias), 'ro': readonly}
                    yield share, bind

        config = self._get(container)
        c_instances = instances or config.instances or [None]
        used_volumes = (self._cname(n) for n in itertools.chain(config.uses, config.attaches))
        c_volumes_from = list(itertools.chain(volumes_from or [], used_volumes)) or None
        c_links = dict((self._cname(name), alias) for name, alias in config.links) or None
        if links:
            c_links.update(links)
        if config.start_options:
            if callable(config.start_options):
                c_kwargs = config.start_options()
            else:
                c_kwargs = config.start_options.copy()
            c_kwargs.update(kwargs)
        else:
            c_kwargs = kwargs

        for i in c_instances:
            c_name = self._cname(container, i)
            host_binds = dict(_get_host_binds(i))
            if binds:
                host_binds.update(binds)
            c_binds = host_binds or None
            self._client.start(c_name, binds=c_binds, volumes_from=c_volumes_from, links=c_links, **c_kwargs)

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

    def create(self, container, instances=None, autocreate_dependencies=True, autocreate_attached=True,
               autocreate_baseimage=DEFAULT_BASEIMAGE, **kwargs):
        """
        Creates container instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance name to create. If not specified, will create all instances as specified in the
         configuration (or just one default instance).
        :type instances: tuple or list
        :param autocreate_dependencies: Resolve and create dependency containers.
        :type autocreate_dependencies: bool
        :param autocreate_attached: Create attached volumes (also applies to all dependencies, if applicable).
        :type autocreate_attached: bool
        :param autocreate_baseimage: Base image for creating attached volumes.
        :type autocreate_baseimage: unicode
        :param kwargs: Additional kwargs for creating the container. `volumes` and `environment` enhance the generated
         arguments; `user` overrides the user from the container configuration.
        :return: List of tuples with container aliases and names of container instances. Does not include attached
         containers.
        """

        def _create_main_container():
            if autocreate_attached:
                self.create_attached_volumes(container, autocreate_baseimage)
            return [ci for ci in self._get_instance_containers(container, instances, default_volumes, default_user, **kwargs)]

        def _create_dependent_containers(c_name):
            if autocreate_attached:
                self.create_attached_volumes(c_name, autocreate_baseimage)
            return [ci for ci in self._get_instance_containers(c_name)]

        default_volumes = kwargs.pop('volumes', None)
        default_user = kwargs.pop('user', None)
        if autocreate_dependencies:
            dependencies = ContainerDependencyResolver(self._map).get_dependencies(container)
            created_containers = [_create_dependent_containers(dependent_container)
                                  for dependent_container in reversed(dependencies)]

            created_containers.append(_create_main_container())
            return list(itertools.chain.from_iterable(created_containers))
        return _create_main_container()

    def start(self, container, instances=None, autostart_dependencies=True, **kwargs):
        """
        Starts instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to start. If not specified, will start all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param autostart_dependencies: Resolve and start dependency containers.
        :type autostart_dependencies: bool
        :param kwargs: Additional kwargs for starting the container. `binds` and `volumes_from` will enhance the
         generated arguments.
        """
        default_binds = kwargs.pop('binds', {})
        default_volumes_from = kwargs.pop('volumes_from', [])
        if autostart_dependencies:
            dependencies = ContainerDependencyResolver(self._map).get_dependencies(container)
            for dependent_container in reversed(dependencies):
                self._start_instance_containers(dependent_container)

        self._start_instance_containers(container, instances, default_binds, default_volumes_from, **kwargs)

    def stop(self, container, instances=None, autostop_dependent=True, **kwargs):
        """
        Stops instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to stop. If not specified, will stop all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param autostop_dependent: Resolve and stop dependent containers.
        :type autostop_dependent: bool
        :param kwargs: Additional kwargs for stopping the container.
        """
        def _stop_container(c_name, c_instances=None):
            lc_instances = c_instances or self._get(c_name).instances or [None]
            for i in lc_instances:
                lc_name = self._cname(c_name, i)
                try:
                    self._client.stop(lc_name, **kwargs)
                except APIError as e:
                    if e.response.status_code != 404:
                        self._client.push_log("Failed to stop container '{0}'.".format(e))

        if autostop_dependent:
            resolver = ContainerDependencyResolver()
            resolver.update_backward(self._map)
            dependencies = resolver.get_dependencies(container)
            for dependent_container in reversed(dependencies):
                _stop_container(dependent_container, **kwargs)

        _stop_container(container, instances, **kwargs)

    def remove(self, container, instances=None):
        """
        Remove instances from a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        """
        c_instances = instances or [None]
        for instance in c_instances:
            c_name = self._cname(container, instance)
            self._remove_container(c_name)

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
