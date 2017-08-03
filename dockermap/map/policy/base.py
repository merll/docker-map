# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from six import iteritems

from ... import DEFAULT_COREIMAGE, DEFAULT_BASEIMAGE, DEFAULT_HOSTNAME_REPLACEMENT, DEFAULT_PRESET_NETWORKS
from ...functional import resolve_value
from .cache import ContainerCache, ImageCache, NetworkCache
from .dep import ContainerDependencyResolver

log = logging.getLogger(__name__)


class BasePolicy(object):
    """
    Abstract base class providing the basic infrastructure for generating actions based on container state.

    :param container_maps: Container maps.
    :type container_maps: dict[unicode | str, dockermap.map.config.main.ContainerMap]
    :param clients: Dictionary of clients.
    :type clients: dict[unicode | str, dockermap.map.config.client.ClientConfiguration]
    """
    core_image = DEFAULT_COREIMAGE
    base_image = DEFAULT_BASEIMAGE
    default_client_name = '__default__'
    hostname_replace = DEFAULT_HOSTNAME_REPLACEMENT
    default_network_names = ['bridge']

    def __init__(self, container_maps, clients):
        self._maps = {
            map_name: map_contents.get_extended_map()
            for map_name, map_contents in iteritems(container_maps)
        }
        self._clients = clients
        self._container_names = ContainerCache(clients)
        self._network_names = NetworkCache(clients)
        self._images = ImageCache(clients)
        self._f_resolver = ContainerDependencyResolver()
        self._r_resolver = ContainerDependencyResolver()
        for m in self._maps.values():
            depdendency_items = m.dependency_items()
            self._f_resolver.update(depdendency_items)
            self._r_resolver.update_backward(depdendency_items)

    @classmethod
    def cname(cls, map_name, container, instance=None):
        """
        Generates a container name that should be used for creating new containers and checking the status of existing
        containers.

        In this implementation, the format will be ``<map name>.<container name>.<instance>``. If no instance is
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
    def nname(cls, map_name, network_name):
        """
        Generates a network name that should be used for creating new networks and checking the status of existing
        networks on the client.

        In this implementation, the format will be ``<map name>.<network name>``.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param network_name: Network configuration name.
        :type network_name: unicode | str
        :return: Network name.
        :rtype: unicode | str
        """
        if network_name in DEFAULT_PRESET_NETWORKS:
            return network_name
        return '{0}.{1}'.format(map_name, network_name)

    @classmethod
    def image_name(cls, image, container_map=None):
        """
        Generates the full image name that should be used when creating a new container.

        This implementation applies the following rules:

        * If the image name starts with ``/``, the following image name is returned.
        * If ``/`` is found anywhere else in the image name, it is assumed to be a repository-prefixed image and
          returned as it is.
        * Otherwise, if the given container map has a repository prefix set, this is prepended to the image name.
        * In any other case, the image name is not modified.

        Where there is a tag included in the ``image`` name, it is not modified. If it is not, the default tag from the
        container map, or ``latest`` is used.

        :param image: Image name.
        :type image: unicode | str
        :param container_map: Container map object, defining a default tag and repository if not specified by the
          ``image``.
        :type container_map: dockermap.map.config.main.ContainerMap
        :return: Image name, where applicable prefixed with a repository.
        :rtype: unicode | str
        """
        if '/' in image:
            if image[0] == '/':
                image_tag = image[1:]
            else:
                image_tag = image
        else:
            default_prefix = resolve_value(container_map.repository) if container_map else None
            if default_prefix:
                image_tag = '{0}/{1}'.format(default_prefix, image)
            else:
                image_tag = image
        if ':' in image:
            return image_tag
        default_tag = resolve_value(container_map.default_tag) if container_map else None
        return '{0}:{1}'.format(image_tag, default_tag or 'latest')

    @classmethod
    def get_hostname(cls, container_name, client_name=None):
        """
        Determines the host name of a container. In this implementation, replaces all dots and underscores of a
        container name with a dash; then attaches another dash with the client name, unless there is just one default
        client.

        :param container_name: Name of the container.
        :type container_name: unicode | str
        :param client_name: Name of the client configuration, where applicable.
        :type client_name: unicode | str
        :return: Host name.
        :rtype: unicode | str
        """
        base_name = container_name
        for old, new in cls.hostname_replace:
            base_name = base_name.replace(old, new)
        if not client_name or client_name == cls.default_client_name:
            return base_name
        client_suffix = client_name
        for old, new in cls.hostname_replace:
            client_suffix = client_suffix.replace(old, new)
        return '{0}-{1}'.format(base_name, client_suffix)

    def get_clients(self, c_map, c_config=None):
        """
        Returns the client configuration names for a given item configuration or map. If there are no clients specified
        for the configuration, the list defaults to the one globally specified for the given map. If that is not defined
        either, the default client is returned.

        :param c_map: Container map instance.
        :type c_map: dockermap.map.config.main.ContainerMap
        :param c_config: Optional container configuration object.
        :type c_config: dockermap.map.config.ContainerConfiguration
        :return: Client configuration names.
        :rtype: list[unicode | str]
        """
        if c_config and c_config.clients:
            return c_config.clients
        if c_map.clients:
            return c_map.clients
        return [self.default_client_name]

    def get_dependencies(self, config_id):
        """
        Generates the list of dependency containers, in reverse order (i.e. the last dependency coming first).

        :param config_id: MapConfigId tuple.
        :type config_id: dockermap.map.input.MapConfigId
        :return: Dependency configuration types, container map names, configuration names, and instances.
        :rtype: collections.Iterable[(unicode | str, unicode | str, unicode | str, unicode | str)]
        """
        return self._f_resolver.get_dependencies(config_id)

    def get_dependents(self, config_id):
        """
        Generates the list of dependent containers, in reverse order (i.e. the last dependent coming first).

        :param config_id: MapConfigId tuple.
        :type config_id: dockermap.map.input.MapConfigId
        :return: Dependent configuration types, container map names, configuration names, and instances.
        :rtype: collections.Iterable[(unicode | str, unicode | str, unicode | str, unicode | str)]
        """
        return self._r_resolver.get_dependencies(config_id)

    @property
    def container_maps(self):
        """
        Container maps with container configurations to base actions on.

        :return: Dictionary of container maps.
        :rtype: dict[unicode | str, dockermap.map.config.main.ContainerMap]
        """
        return self._maps

    @property
    def clients(self):
        """
        Docker client objects and configurations.

        :return: Dictionary of Docker client objects.
        :rtype: dict[unicode | str, dockermap.map.config.client.ClientConfiguration]
        """
        return self._clients

    @property
    def container_names(self):
        """
        Names of existing containers on each client.

        :return: Dictionary of container names.
        :rtype: dict[unicode | str, dockermap.map.policy.cache.CachedContainerNames]
        """
        return self._container_names

    @property
    def images(self):
        """
        Names of images on each client.

        :return: Dictionary of image names per client.
        :rtype: dict[unicode | str, dockermap.map.policy.cache.CachedImages]
        """
        return self._images

    @property
    def network_names(self):
        """
        Name of existing networks on each client.

        :return: Dictionary of network names.
        :rtype: dict[unicode | str, dockermap.map.policy.cache.CachedNetworkNames]
        """
        return self._network_names
