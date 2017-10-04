# -*- coding: utf-8 -*-
from __future__ import unicode_literals


class CachedItems(object):
    """
    Abstract implementation for a caching collection of client names or ids.

    :param client: Client object.
    :type client: docker.client.Client
    """
    def __init__(self, client):
        self._client = client
        super(CachedItems, self).__init__()
        self.refresh()

    def refresh(self):
        """
        Forces a refresh of the cached items. Does not need to return anything.
        """
        raise NotImplementedError("Method 'refresh' is not implemented.")


class CachedImages(CachedItems, dict):
    """
    Dictionary of image names and ids, which also keeps track of the client object to pull images if necessary.
    """
    def _update(self, image_list):
        for image in image_list:
            tags = image.get('RepoTags')
            if tags:
                self.update({tag: image['Id'] for tag in tags})

    def refresh(self):
        """
        Fetches image and their ids from the client.
        """
        if not self._client:
            return
        current_images = self._client.images()
        self.clear()
        self._update(current_images)
        for image in current_images:
            tags = image.get('RepoTags')
            if tags:
                self.update({tag: image['Id'] for tag in tags})

    def refresh_repo(self, name):
        if not self._client:
            return
        self._update(self._client.images(name=name))


class CachedContainerNames(CachedItems, dict):
    def refresh(self):
        """
        Fetches all current container names from the client, along with their id.
        """
        if not self._client:
            return
        current_containers = self._client.containers(all=True)
        self.clear()
        for container in current_containers:
            container_names = container.get('Names')
            if container_names:
                c_id = container['Id']
                self.update((name[1:], c_id)
                            for name in container_names)


class CachedNetworkNames(CachedItems, dict):
    def refresh(self):
        """
        Fetches all current network names from the client, along with their id.
        """
        if not self._client:
            return
        current_networks = self._client.networks()
        self.clear()
        self.update((net['Name'], net['Id'])
                    for net in current_networks)


class CachedVolumeNames(CachedItems, set):
    def refresh(self):
        """
        Fetches all current network names from the client.
        """
        if not self._client:
            return
        current_volumes = self._client.volumes()['Volumes']
        self.clear()
        if current_volumes:
            self.update(vol['Name'] for vol in current_volumes)


class DockerHostItemCache(dict):
    """
    Abstract class for implementing caches of items (containers, images) present on the Docker client, so that
    their existence does not have to be checked separately for every action.

    :param clients: Dictionary of clients with alias and client object.
    :type clients: dict[unicode | str, dockermap.map.config.client.ClientConfiguration]
    """
    item_class = None

    def __init__(self, clients, *args, **kwargs):
        self._clients = clients
        super(DockerHostItemCache, self).__init__(*args, **kwargs)

    def __getitem__(self, item):
        """
        Retrieves the items associated with the given client. Returned results are cached for later use.

        :param item: Client name.
        :type item: unicode | str
        :return: Items in the cache.
        """
        if item not in self:
            return self.refresh(item)
        return super(DockerHostItemCache, self).__getitem__(item)

    def refresh(self, item):
        """
        Forces a refresh of a cached item.

        :param item: Client name.
        :type item: unicode | str
        :return: Items in the cache.
        :rtype: DockerHostItemCache.item_class
        """
        client = self._clients[item].get_client()
        self[item] = val = self.item_class(client)
        return val


class ImageCache(DockerHostItemCache):
    """
    Fetches and caches image names and ids from a Docker host.
    """
    item_class = CachedImages


class ContainerCache(DockerHostItemCache):
    """
    Fetches and caches container names from a Docker host.
    """
    item_class = CachedContainerNames


class NetworkCache(DockerHostItemCache):
    """
    Fetches and caches network names from a Docker host.
    """
    item_class = CachedNetworkNames

    def refresh(self, item):
        client_config = self._clients[item]
        if client_config.supports_networks:
            return super(NetworkCache, self).refresh(item)
        raise ValueError("Client does not support network configuration.", item)


class VolumeCache(DockerHostItemCache):
    """
    Fetches and caches volume names from a Docker host.
    """
    item_class = CachedVolumeNames

    def refresh(self, item):
        client_config = self._clients[item]
        if client_config.supports_volumes:
            return super(VolumeCache, self).refresh(item)
        raise ValueError("Client does not support volume configuration.", item)
