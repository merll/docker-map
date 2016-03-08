# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from . import STATE_ABSENT
from .base import DependencyStateGenerator


class InitialStateGenerator(DependencyStateGenerator):
    def get_container_state(self, map_name, container_map, config_name, container_config, client_name, client_config,
                            client, instance_alias, config_flags=0):
        """
        Assumes every container to be absent. This is intended for testing and situations where the actual state
        cannot be determined.

        :param map_name: Container map name.
        :type map_name: unicode | str
        :param container_map: Container map instance.
        :type container_map: dockermap.map.container.ContainerMap
        :param config_name: Container configuration name.
        :type config_name: unicode | str
        :param container_config: Container configuration object.
        :type container_config: dockermap.map.config.ContainerConfiguration
        :param client_name: Client name.
        :type client_name: unicode | str
        :param client_config: Client configuration object.
        :type client_config: dockermap.map.config.ClientConfiguration
        :param client: Docker client.
        :type client: docker.client.Client
        :param instance_alias: Container instance name or attached alias.
        :type instance_alias: unicode | str
        :param config_flags: Config flags on the container.
        :type config_flags: int
        :return: Tuple of container inspection detail, and the base state information derived from that.
        :rtype: (dict | NoneType, unicode | str, int, dict)
        """
        return None, STATE_ABSENT, 0, {}
