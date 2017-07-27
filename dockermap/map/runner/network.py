# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..action import (ACTION_DISCONNECT, ACTION_CONNECT, ACTION_CREATE, ACTION_REMOVE, C_UTIL_ACTION_CONNECT_ALL,
                      N_UTIL_ACTION_DISCONNECT_ALL)
from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_NETWORK


class NetworkUtilMixin(object):
    action_method_names = [
        (ITEM_TYPE_NETWORK, ACTION_CREATE, 'create_network'),
        (ITEM_TYPE_NETWORK, ACTION_REMOVE, 'remove_network'),
        (ITEM_TYPE_NETWORK, N_UTIL_ACTION_DISCONNECT_ALL, 'disconnect_all_containers'),

        (ITEM_TYPE_CONTAINER, ACTION_CONNECT, 'connect_networks'),
        (ITEM_TYPE_CONTAINER, ACTION_DISCONNECT, 'disconnect_networks'),
        (ITEM_TYPE_CONTAINER, C_UTIL_ACTION_CONNECT_ALL, 'connect_all_networks'),
    ]

    def create_network(self, action, n_name, **kwargs):
        """
        Creates a configured network.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param n_name: Network name.
        :type n_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        c_kwargs = self.get_network_create_kwargs(action, n_name, **kwargs)
        return action.client.create_network(**c_kwargs)

    def remove_network(self, action, n_name, **kwargs):
        """
        Removes a network.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param n_name: Network name or id.
        :type n_name: unicode | str
        :param kwargs: Additional keyword arguments.
        :type kwargs: dict
        """
        c_kwargs = self.get_network_remove_kwargs(action, n_name, **kwargs)
        return action.client.remove_network(**c_kwargs)

    def disconnect_all_containers(self, action, network_name, containers, **kwargs):
        """
        Disconnects all containers from a network.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param network_name: Network name or id.
        :type network_name: unicode | str
        :param containers: Container names or ids.
        :type containers: collections.Iterable[unicode | str]
        :param kwargs: Additional keyword arguments.
        :type kwargs: dict
        """
        client = action.client
        for c_name in containers:
            disconnect_kwargs = self.get_network_disconnect_kwargs(action, network_name, c_name, kwargs=kwargs)
            client.disconnect_container_from_network(**disconnect_kwargs)

    def connect_networks(self, action, container_name, endpoints, **kwargs):
        """
        Connects a container to a set of configured networks.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container names or id.
        :type container_name: unicode | str
        :param endpoints: Network endpoint configurations.
        :type endpoints: collections.Iterable[dockermap.map.input.NetworkEndpoint]
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        client = action.client
        map_name = action.config_id.map_name
        nname = self._policy.nname
        for network_endpoint in endpoints:
            network_name = nname(map_name, network_endpoint.network_name)
            connect_kwargs = self.get_network_connect_kwargs(action, network_name, container_name, network_endpoint,
                                                             kwargs=kwargs)
            client.connect_container_to_network(**connect_kwargs)

    def disconnect_networks(self, action, container_name, networks, **kwargs):
        """
        Connects a container to a set of networks.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container names or id.
        :type container_name: unicode | str
        :param networks: List of network names or ids.
        :type networks: list[unicode | str]
        :param kwargs: Additional keyword arguments.
        :type kwargs: dict
        """
        client = action.client
        for n_name in networks:
            disconnect_kwargs = self.get_network_disconnect_kwargs(action, n_name, container_name, kwargs=kwargs)
            client.disconnect_container_from_network(**disconnect_kwargs)

    def connect_all_networks(self, action, container_name, **kwargs):
        """
        Connects a container to all of its configured networks.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container names or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        self.connect_networks(action, container_name, action.config.networks, **kwargs)
