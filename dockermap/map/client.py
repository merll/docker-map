# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple
import logging
import re

import six
from docker.errors import APIError

from ..shortcuts import get_user_group
from .container import ContainerMap
from .policy import (ACTION_CREATE, ACTION_START, ACTION_RESTART, ACTION_PREPARE, ACTION_STOP, ACTION_REMOVE,
                     ResumeUpdatePolicy)


EXITED_REGEX = 'Exited \((\d+)\)'
exited_pattern = re.compile(EXITED_REGEX)

MapClient = namedtuple('MapClient', ('container_map', 'client'))


def _run_and_dispose(client, image, entrypoint, command, user, volumes_from):
    tmp_container = client.create_container(image, entrypoint=entrypoint, command=command, user=user)['Id']
    try:
        client.start(tmp_container, volumes_from=volumes_from)
        client.wait(tmp_container)
        client.push_container_logs(tmp_container)
    finally:
        client.remove_container(tmp_container)


def _adjust_permissions(client, image, container_name, path, user, permissions):
    if not user and not permissions:
        return
    if user:
        client.push_log("Adjusting user for container '{0}' to '{1}'.".format(container_name, user))
        _run_and_dispose(client, image, None, ['chown', '-R', get_user_group(user), path], 'root', [container_name])
    if permissions:
        client.push_log("Adjusting permissions for container '{0}' to '{1}'.".format(container_name, permissions))
        _run_and_dispose(client, image, None, ['chmod', '-R', permissions, path], 'root', [container_name])


class MappingDockerClient(object):
    """
    Reflects a :class:`~dockermap.map.container.ContainerMap` instance on a Docker client
    (:class:`~dockermap.map.base.DockerClientWrapper`). The ``policy_class`` determines if and how dependencies
    are being considered during creation, starting, stopping, and removal of containers.

    If only one container map is provided, it will be the default map for all operations. If multiple container maps
    are used, the list can contain instances of clients to be used. In that case, the ``docker_client`` argument is
    ignored.

    Image names, container status, and dependencies are cached. In order to force a refresh, use :meth:`refresh_names`.
    It is also cleared on every change of ``policy_class``.

    :param container_maps: :class:`~dockermap.map.container.ContainerMap` instance or a tuple or list of such instances
      along with an associated instance.
    :type container_maps: dockermap.map.container.ContainerMap or
      list[(dockermap.map.container.ContainerMap, dockermap.map.base.DockerClientWrapper)]
    :param docker_client: Default :class:`~dockermap.map.base.DockerClientWrapper` instance.
    :type docker_client: dockermap.map.base.DockerClientWrapper
    :param policy_class: Policy class based on :class:`~dockermap.map.policy.base.BasePolicy` for generating container
      actions.
    :type policy_class: class
    """
    def __init__(self, container_maps=None, docker_client=None, policy_class=ResumeUpdatePolicy):
        def _map_client(item):
            if isinstance(item, (list, tuple)):
                return item[0].name, MapClient(item[0], item[1])
            return item.name, MapClient(item, docker_client)

        if isinstance(container_maps, ContainerMap):
            self._default_map = container_maps.name
            self._maps = {container_maps.name: MapClient(container_maps, docker_client)}
        elif isinstance(container_maps, (list, tuple)):
            self._default_map = None
            self._maps = dict(map(_map_client, container_maps))
        else:
            raise ValueError("Unexpected type of container_maps argument: {0}".format(type(container_maps)))
        self._image_tags = {}
        self._policy_class = policy_class
        self._policy = None

    def _get_status(self):
        """
        :rtype: dict
        """
        def _extract_status():
            for c_map, client in self._maps.values():
                map_containers = client.containers(all=True)
                for container in map_containers:
                    c_status = container['Status']
                    if c_status == '':
                        cs = False
                    elif c_status.startswith('Up') or c_status.startswith('Restarting'):
                        cs = True
                    else:
                        exit_match = exited_pattern.match(c_status)
                        if exit_match:
                            cs = int(exit_match.group(1))
                        else:
                            cs = None
                    for name in container['Names']:
                        yield name[1:], cs

        return dict(_extract_status())

    def _inspect_container(self, map_name, container):
        """
        :type map_name: unicode
        :type container: unicode
        :rtype: dict
        """
        client = self._get_client(map_name)
        return client.inspect_container(container)

    def _get_image_tags(self, map_name, force=False):
        """
        :type map_name: unicode
        :type force: bool
        :return: dict
        """
        tags = self._image_tags.get(map_name) if not force else None
        if tags is None:
            client = self._get_client(map_name)
            tags = client.get_image_tags()
            self._image_tags[map_name] = tags
        return tags

    def _get_client(self, map_name):
        """
        :type map_name: unicode
        :rtype: dockermap.map.base.DockerClientWrapper
        """
        c_map = self._maps.get(map_name)
        if not c_map:
            raise ValueError("No map found with name '{0}'.".format(map_name))
        return c_map[1]

    def _ensure_images(self, map_name, *images):
        """
        :type map_name: unicode
        :type images: unicode
        :rtype: dict
        """
        def _check_image(image_name):
            image_name, __, tag = image_name.partition(':')
            if tag:
                full_name = image_name
            else:
                full_name = ':'.join((image_name, 'latest'))
            if full_name not in map_images:
                map_client.import_image(image=image_name, tag=tag or 'latest')
                return True
            return False

        map_client = self._get_client(map_name)
        map_images = set(self._get_image_tags(map_name).keys())
        new_images = [_check_image(image) for image in images]
        if any(new_images):
            self._get_image_tags(map_name, True)

    def get_policy(self):
        """
        Returns an instance of :attr:`~policy_class`. When instantiating, the following items are collected:

        * A dictionary of container maps.
        * A list of container names marked as persistent.
        * A dictionary of image tags and ids.
        * A dictionary of functions to evaluate a detailed container status at runtime.

        A dictionary of the basic container status is refreshed on each call. In order to force a refresh on other
        items, use :meth:`~refresh_names`.

        :return: An instance of the current policy class.
        :rtype: dockermap.map.policy.BasePolicy
        """
        if not self._policy:
            map_dict = dict((name, mc[0]) for name, mc in six.iteritems(self._maps))
            persistent_list = self.list_persistent_containers()
            status_dict = dict((name, lambda container_name: self._inspect_container(name, container_name))
                               for name in self._maps.keys())
            image_dict = dict((name, lambda image_name: self._get_image_tags(name).get(image_name))
                              for name in self._maps.keys())
            self._policy = self._policy_class(map_dict, persistent_list, status_dict, image_dict)
        self._policy.status = self._get_status()
        return self._policy

    def run_action_list(self, actions, apply_kwargs=None, raise_on_error=False):
        """
        Performs the actions on Docker containers defined by the given list.

        :param actions: An iterable of ContainerAction tuples. It can also be a generator.
        :type actions: list[dockermap.map.policy.ContainerAction]
        :param apply_kwargs: Optional dictionary of actions to apply certain keyword arguments to.
        :type apply_kwargs: dict
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored on stop and removal.
        :type raise_on_error: bool
        :return: Iterable of created containers.
        :rtype: generator
        """
        run_kwargs = apply_kwargs or {}
        for action, flags, map_name, container, kwargs in actions:
            client = self._get_client(map_name)
            c_kwargs = run_kwargs.get((action, flags))
            if c_kwargs:
                a_kwargs = kwargs.copy() if kwargs else {}
                a_kwargs.update(c_kwargs)
            else:
                a_kwargs = kwargs or {}
            if action == ACTION_CREATE:
                image = a_kwargs.pop('image')
                name = a_kwargs.pop('name', container)
                self._ensure_images(map_name, image)
                yield client.create_container(image, name=name, **a_kwargs)
            elif action == ACTION_START:
                client.start(container, **a_kwargs)
            elif action == ACTION_PREPARE:
                image = a_kwargs.pop('image')
                client.wait(container)
                _adjust_permissions(client, image, container, **a_kwargs)
            elif action == ACTION_RESTART:
                client.restart(container, **a_kwargs)
            elif action == ACTION_STOP:
                try:
                    client.stop(container, **a_kwargs)
                except APIError as e:
                    if e.response.status_code != 404:
                        client.push_log("Failed to stop container '{0}': {1}".format(container, e.explanation),
                                        logging.ERROR)
                        if raise_on_error:
                            raise e
            elif action == ACTION_REMOVE:
                try:
                    client.remove_container(container, **a_kwargs)
                except APIError as e:
                    if e.response.status_code != 404:
                        client.push_log("Failed to remove container '{0}': {1}".format(container, e.explanation),
                                        logging.ERROR)
                        if raise_on_error:
                            raise e
            else:
                raise ValueError("Unrecognized action {0}.".format(action))

    def create(self, container, instances=None, map_name=None, **kwargs):
        """
        Creates container instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance name to create. If not specified, will create all instances as specified in the
         configuration (or just one default instance).
        :type instances: tuple or list
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container creation.
        :return: List of created containers.
        :rtype: list[dict]
        """
        apply_kwargs = {
            (ACTION_CREATE, 0): kwargs,
        }
        create_actions = self.get_policy().create_actions(map_name or self._default_map, container, instances)
        return list(self.run_action_list(create_actions, apply_kwargs))

    def start(self, container, instances=None, map_name=None, **kwargs):
        """
        Starts instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to start. If not specified, will start all instances as specified in the
         configuration (or just one default instance).
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :type instances: iterable
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container start.
        :return: List of created containers.
        :rtype: list[dict]
        """
        apply_kwargs = {
            (ACTION_START, 0): kwargs,
        }
        start_actions = self.get_policy().start_actions(map_name or self._default_map, container, instances)
        return list(self.run_action_list(start_actions, apply_kwargs))

    def restart(self, container, instances=None, map_name=None, **kwargs):
        """
        Restarts instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to stop. If not specified, will restart all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container restart.
        :return: List of created containers.
        :rtype: list[dict]
        """
        apply_kwargs = {
            (ACTION_RESTART, 0): kwargs,
        }
        restart_actions = self.get_policy().restart_actions(map_name or self._default_map, container, instances)
        return list(self.run_action_list(restart_actions, apply_kwargs))

    def stop(self, container, instances=None, map_name=None, raise_on_error=False, **kwargs):
        """
        Stops instances for a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to stop. If not specified, will stop all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored on stop and removal.
        :type raise_on_error: bool
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container stop.
        :return: List of created containers.
        :rtype: list[dict]
        """
        apply_kwargs = {
            (ACTION_STOP, 0): kwargs,
        }
        stop_actions = self.get_policy().stop_actions(map_name or self._default_map, container, instances)
        return list(self.run_action_list(stop_actions, apply_kwargs, raise_on_error=raise_on_error))

    def remove(self, container, instances=None, map_name=None, raise_on_error=False, **kwargs):
        """
        Remove instances from a container configuration.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored on stop and removal.
        :type raise_on_error: bool
        :param kwargs: Additional kwargs. If multiple actions are resulting from this, they will only be applied to
          the main container removal.
        :return: List of created containers.
        :rtype: list[dict]
        """
        apply_kwargs = {
            (ACTION_REMOVE, 0): kwargs,
        }
        remove_actions = self.get_policy().remove_actions(map_name or self._default_map, container, instances)
        return list(self.run_action_list(remove_actions, apply_kwargs, raise_on_error=raise_on_error))

    def startup(self, container, instances=None, map_name=None, raise_on_error=False):
        """
        Start up container instances from a container configuration. Typically this means creating and starting
        containers and their dependencies. Note that not all policy classes necessarily implement this method.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored on stop and removal.
        :type raise_on_error: bool
        :return:
        """
        startup_actions = self.get_policy().startup_actions(map_name or self._default_map, container, instances)
        return list(self.run_action_list(startup_actions, raise_on_error=raise_on_error))

    def shutdown(self, container, instances=None, map_name=None, raise_on_error=False):
        """
        Shut down container instances from a container configuration. Typically this means stopping and removing
        containers. Note that not all policy classes necessarily implement this method.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored on stop and removal.
        :type raise_on_error: bool
        :return:
        """
        shutdown_actions = self.get_policy().shutdown_actions(map_name or self._default_map, container, instances)
        return list(self.run_action_list(shutdown_actions, raise_on_error=raise_on_error))

    def update(self, container, instances=None, map_name=None, raise_on_error=False):
        """
        Updates instances from a container configuration. Typically this means restarting or recreating containers based
        on detected changes in the configuration or environment.  Note that not all policy classes necessarily implement
        this method.

        :param container: Container name.
        :type container: unicode
        :param instances: Instance names to remove. If not specified, will remove all instances as specified in the
         configuration (or just one default instance).
        :type instances: iterable
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored on stop and removal.
        :type raise_on_error: bool
        """
        update_actions = self.get_policy().update_actions(map_name or self._default_map, container, instances)
        return list(self.run_action_list(update_actions, raise_on_error=raise_on_error))

    def wait(self, container, instance=None, map_name=None, log=True):
        """
        Wait for a container.

        :param container: Container name.
        :type container: unicode
        :param instance: Instance name to remove. If not specified, removes the default instance.
        :type instance: unicode
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param log: Log the container output after waiting.
        :type log: bool
        """
        c_map_name = map_name or self._default_map
        client = self._get_client(c_map_name)
        c_name = self._policy_class.cname(c_map_name, container, instance)
        client.wait(c_name)
        if log:
            client.push_container_logs(c_name)

    def wait_and_remove(self, container, instance=None, map_name=None, log=True, **kwargs):
        """
        Wait for, and then remove a container. Does not resolve dependencies.

        :param container: Container name.
        :type container: unicode
        :param instance: Instance name to remove. If not specified, removes the default instance.
        :type instance: unicode
        :param map_name: Container map name. Optional - if not provided the default map is used.
        :type map_name: unicode
        :param log: Log the container output before removing it.
        :type log: bool
        :param kwargs: Additional kwargs for removing the container.
        """
        c_map_name = map_name or self._default_map
        client = self._get_client(c_map_name)
        c_name = self._policy_class.cname(c_map_name, container, instance)
        self.wait(container, instance=instance, map_name=c_map_name, log=log)
        client.remove_container(c_name, **kwargs)

    def refresh_names(self):
        """
        Invalidates the policy name and status cache.
        """
        self._policy = None

    def list_persistent_containers(self, map_name=None):
        """
        Lists the names of all persistent containers on the specified map or all maps. Attached containers are always
        considered persistent.

        :param map_name: Container map name. Optional, only returns persistent containers from the specified map.
        :type map_name: unicode
        :return: List of container names.
        :rtype: list[unicode]
        """
        def _container_names():
            for c_map, __ in maps:
                for container, config in c_map:
                    for ac in config.attaches:
                        yield cname_func(c_map.name, ac)
                    if config.persistent:
                        if config.instances:
                            for ci in config.instances:
                                yield cname_func(c_map.name, container, ci)
                        else:
                            yield cname_func(c_map.name, container)

        cname_func = self._policy_class.cname
        maps = (self._maps[map_name], ) if map_name else self._maps.values()
        return list(_container_names())

    @property
    def maps(self):
        """
        Container maps.

        :return: A dictionary with container map names as keys, and container map and client as values.
        :rtype: dict[unicode, MapClient]
        """
        return self._maps

    @property
    def default_map(self):
        """
        The default map to use for any actions, if not otherwise specified.

        :return: Container map name.
        :rtype: unicode
        """
        return self._default_map

    @default_map.setter
    def default_map(self, value):
        if value in self._maps:
            raise ValueError("Default name must match an available map name.")
        self._default_map = value

    @property
    def policy_class(self):
        """
        The policy class, that transforms commands into actions on containers, considering potential dependencies.

        :return: Subclass of :class:`~dockermap.map.policy.base.BasePolicy`.
        :rtype: class
        """
        return self._policy_class

    @policy_class.setter
    def policy_class(self, value):
        self._policy = None
        self._policy_class = value
