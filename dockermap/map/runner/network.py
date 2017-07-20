# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..action import C_UTIL_ACTION_CONNECT, N_UTIL_ACTION_DISCONNECT_ALL
from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_NETWORK


class NetworkUtilMixin(object):
    action_method_names = [
        (ITEM_TYPE_CONTAINER, C_UTIL_ACTION_CONNECT, 'connect_networks'),
        (ITEM_TYPE_NETWORK, N_UTIL_ACTION_DISCONNECT_ALL, 'disconnect_all_containers'),
    ]

    def connect_networks(self, action, container_name, networks, **kwargs):
        """
        Connects a container to a set of networks.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container names or id.
        :type container_name: unicode | str
        :param networks: Network names or ids.
        :type networks: collections.Iterable[unicode | str}
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        client = action.client
        for n_name in networks:
            connect_kwargs = self.get_network_connect_kwargs(action, n_name, container_name, kwargs=kwargs)
            client.connect_container_to_network(**connect_kwargs)

    def disconnect_all_containers(self, action, network_name, containers, **kwargs):
        """
        Disconnects all containers from the network

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param network_name: Network name or id.
        :type network_name: unicode | str
        :param containers: Container names or ids.
        :type containers: collections.Iterable[unicode | str]
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        client = action.client
        for c_name in containers:
            disconnect_kwargs = self.get_network_disconnect_kwargs(action, network_name, c_name, kwargs=kwargs)
            client.disconnect_container_from_network(**disconnect_kwargs)
