# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from itertools import islice

from ..action import Action, ContainerUtilAction, NetworkUtilAction
from ..input import ItemType


class NetworkUtilMixin(object):
    action_method_names = [
        (ItemType.NETWORK, NetworkUtilAction.DISCONNECT_ALL, 'disconnect_all_containers'),

        (ItemType.CONTAINER, Action.CONNECT, 'connect_networks'),
        (ItemType.CONTAINER, Action.DISCONNECT, 'disconnect_networks'),
        (ItemType.CONTAINER, ContainerUtilAction.CONNECT_ALL, 'connect_all_networks'),
    ]

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

    def connect_networks(self, action, container_name, endpoints, skip_first=False, **kwargs):
        """
        Connects a container to a set of configured networks. By default this assumes the container has just been
        created, so it will skip the first network that is already considered during creation.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container names or id.
        :type container_name: unicode | str
        :param endpoints: Network endpoint configurations.
        :type endpoints: list[dockermap.map.input.NetworkEndpoint]
        :param skip_first: Skip the first network passed in ``endpoints``. Defaults to ``False``, but should be set
          to ``True`` when the container has just been created and the first network has been set up there.
        :type skip_first: bool
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        if not endpoints or (skip_first and len(endpoints) <= 1):
            return
        client = action.client
        map_name = action.config_id.map_name
        nname = self._policy.nname
        if skip_first:
            endpoints = islice(endpoints, 1, None)
        for network_endpoint in endpoints:
            network_name = nname(map_name, network_endpoint.network_name)
            connect_kwargs = self.get_network_connect_kwargs(action, network_name, container_name, network_endpoint,
                                                             kwargs=kwargs)
            client.connect_container_to_network(**connect_kwargs)

    def disconnect_networks(self, action, container_name, networks, **kwargs):
        """
        Disconnects a container from a set of networks.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container names or id.
        :type container_name: unicode | str
        :param networks: List of network names or ids.
        :type networks: collections.Iterable[unicode | str]
        :param kwargs: Additional keyword arguments.
        :type kwargs: dict
        """
        client = action.client
        for n_name in networks:
            disconnect_kwargs = self.get_network_disconnect_kwargs(action, n_name, container_name, kwargs=kwargs)
            client.disconnect_container_from_network(**disconnect_kwargs)

    def connect_all_networks(self, action, container_name, **kwargs):
        """
        Connects a container to all of its configured networks. Assuming that this is typically used after container
        creation, where teh first endpoint is already defined, this skips the first configuration. Pass ``skip_first``
        as ``False`` to change this.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container names or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        kwargs.setdefault('skip_first', True)
        self.connect_networks(action, container_name, action.config.networks, **kwargs)
