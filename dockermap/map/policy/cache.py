# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod


class CachedItems(object):
    """
    Abstract implementation for a caching collection of client names or ids.

    :param client: Client object.
    :type client: docker.client.Client
    """
    __metaclass__ = ABCMeta

    def __init__(self, client, *args, **kwargs):
        self._client = client
        super(CachedItems, self).__init__(*args, **kwargs)
        self.refresh()

    @abstractmethod
    def refresh(self):
        """
        Forces a refresh of the cached items. Does not need to return anything.
        """
        pass


class CachedImages(CachedItems, dict):
    """
    Dictionary of image names and ids, which also keeps track of the client object to pull images if necessary.
    """
    def refresh(self):
        """
        Fetches image and their ids from the client.
        """
        self.clear()
        current_images = self._client.images()
        self.update((tag, i['Id']) for i in current_images for tag in i['RepoTags'])

    def ensure_image(self, image_name):
        """
        Ensures that a particular image is present on the client. If it is not, a new copy is pulled from the server.

        :param image_name: Image name. If it does not include a specific tag, ``latest`` is assumed.
        :type image_name: unicode
        :return: Image id associated with the image name.
        :rtype: unicode
        """
        image, __, tag = image_name.partition(':')
        if tag:
            full_name = image_name
        else:
            full_name = ':'.join((image_name, 'latest'))
        if full_name not in self:
            self._client.import_image(image=image, tag=tag or 'latest')
            self.refresh()
        return self[full_name]


class CachedContainerNames(CachedItems, set):
    def refresh(self):
        """
        Fetches all current container names from the client.
        """
        current_containers = self._client.containers(all=True)
        self.clear()
        self.update(name[1:] for container in current_containers for name in container['Names'])


class DockerHostItemCache(dict):
    """
    Abstract class for implementing caches of items (containers, images) present on the Docker client, so that
    their existence does not have to be checked separately for every action.

    :param clients: Dictionary of clients with alias and client object.
    :type clients: dict[unicode, dockermap.map.config.ClientConfiguration]
    """
    item_class = None

    __metaclass__ = ABCMeta

    def __init__(self, clients, *args, **kwargs):
        self._clients = clients
        super(DockerHostItemCache, self).__init__(*args, **kwargs)

    def __getitem__(self, item):
        """
        Retrieves the items associated with the given client. Returned results are cached for later use.

        :param item: Client name.
        :type item: unicode
        :return: Items in the cache.
        :rtype: any
        """
        if item not in self:
            return self.refresh(item)
        return super(DockerHostItemCache, self).__getitem__(item)

    def refresh(self, item):
        """
        Forces a refresh of a cached item.

        :param item: Client name.
        :type item: unicode
        :return: Items in the cache.
        :rtype: item_class
        """
        client = self._clients[item].get_client()
        val = self.item_class(client)
        self[item] = val
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
