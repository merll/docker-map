# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from six import iteritems, itervalues

from ... import DEFAULT_COREIMAGE, DEFAULT_BASEIMAGE, DEFAULT_HOSTNAME_REPLACEMENT, DEFAULT_PRESET_NETWORKS
from ..input import UsedVolume
from .cache import ContainerCache, ImageCache, NetworkCache, VolumeCache
from .dep import ContainerDependencyResolver, ContainerDependentsResolver

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
        self._maps = maps = {
            map_name: map_contents.get_extended_map()
            for map_name, map_contents in iteritems(container_maps)
        }
        self._clients = clients
        self._container_names = ContainerCache(clients)
        self._network_names = NetworkCache(clients)
        self._volume_names = VolumeCache(clients)
        self._images = ImageCache(clients)
        self._f_resolver = f_resolver = ContainerDependencyResolver()
        self._r_resolver = r_resolver = ContainerDependentsResolver()
        self._default_volume_paths = volume_paths = {}
        self._volume_users = volume_users = {}
        self._volume_permissions = volume_permissions = {}
        for m in itervalues(maps):
            depdendency_items = list(m.dependency_items())
            f_resolver.update(depdendency_items)
            r_resolver.update(depdendency_items)
            volume_paths[m.name] = map_paths = {}
            volume_users[m.name] = map_users = {}
            volume_permissions[m.name] = map_permissions = {}
            default_paths = m.volumes.get_default_paths()
            v_users = m.volumes.get_users()
            v_permissions = m.volumes.get_permissions()
            map_paths.update(default_paths)
            if m.use_attached_parent_name:
                map_paths.update(('{0}.{1}'.format(c_name, a.name),
                                  a.path if isinstance(a, UsedVolume) else default_paths[a.name])
                                 for c_name, c_config in m
                                 for a in c_config.attaches)
                map_users.update(('{0}.{1}'.format(c_name, a.name),
                                  v_users.get(a.name) or c_config.user)
                                 for c_name, c_config in m
                                 for a in c_config.attaches)
                map_permissions.update(('{0}.{1}'.format(c_name, a.name),
                                       v_permissions.get(a.name) or c_config.permissions)
                                       for c_name, c_config in m
                                       for a in c_config.attaches)
            else:
                map_paths.update((a.name,
                                  a.path if isinstance(a, UsedVolume) else default_paths[a.name])
                                 for c_name, c_config in m
                                 for a in c_config.attaches)
                map_users.update((a.name,
                                  v_users.get(a.name) or c_config.user)
                                 for c_name, c_config in m
                                 for a in c_config.attaches)
                map_permissions.update((a.name,
                                       v_permissions.get(a.name) or c_config.permissions)
                                       for c_name, c_config in m
                                       for a in c_config.attaches)

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
        Names of existing networks on each client.

        :return: Dictionary of network names.
        :rtype: dict[unicode | str, dockermap.map.policy.cache.CachedNetworkNames]
        """
        return self._network_names

    @property
    def volume_names(self):
        """
        Names of existing volumes on each client.

        :return: Dictionary of volume names.
        :rtype: dict[unicode | str, dockermap.map.policy.cache.CachedVolumeNames]
        """
        return self._volume_names

    @property
    def default_volume_paths(self):
        """
        Defined volume names of each map, with a dictionary of default container paths per volume alias. Also includes
        paths of attached volumes that are defined directly on container configurations.

        :return: Default volume paths.
        :rtype: dict[unicode | str, dict]
        """
        return self._default_volume_paths

    @property
    def volume_users(self):
        """
        Defined volume names of each map, with a dictionary of the configured user per volume alias. Only applies
        to attached volumes.

        :return: Configured volume paths.
        :rtype: dict[unicode | str, dict]
        """
        return self._volume_users

    @property
    def volume_permissions(self):
        """
        Defined volume names of each map, with a dictionary of the configured permissions per volume alias. Only
        applies to attached volumes.

        :return: Configured volume permissions.
        :rtype: dict[unicode | str, dict]
        """
        return self._volume_permissions
