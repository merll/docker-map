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
    def __init__(self, *args, **kwargs):
        self._updated = set()
        super(CachedImages, self).__init__(*args, **kwargs)

    def refresh(self):
        """
        Fetches image and their ids from the client.
        """
        if not self._client:
            return
        current_images = self._client.images()
        self.clear()
        for image in current_images:
            tags = image.get('RepoTags')
            if tags:
                self.update({tag: image['Id'] for tag in tags})

    def reset_updated(self):
        """
        Resets the cache which images have been pulled (i.e. updated on the default tag.)
        """
        self._updated = set()

    def ensure_image(self, image_name, pull=False, insecure_registry=False):
        """
        Ensures that a particular image is present on the client. If it is not, a new copy is pulled from the server.

        :param image_name: Image name. If it does not include a specific tag, ``latest`` is assumed.
        :type image_name: unicode | str
        :param pull: If the image includes a tag, pull it from the server even if it exists. This is is done only once
          in for the lifecycle of the cache, or unless `:meth:reset_updated` is called.
        :type pull: bool
        :param insecure_registry: Pull from an insecure registry where necessary.
        :type insecure_registry: bool
        :return: Image id associated with the image name.
        :rtype: unicode | str
        """
        image, __, tag = image_name.rpartition(':')
        if image:
            full_name = image_name
        else:
            full_name = '{0}:latest'.format(image_name)
            image = image_name
            tag = 'latest'
        if (pull and full_name not in self._updated) or full_name not in self:
            self._client.pull(repository=image, tag=tag, insecure_registry=insecure_registry)
            images = self._client.images(name=image)
            for new_image in images:
                tags = new_image.get('RepoTags')
                if tags:
                    self._updated.update(tags)
                    self.update({tag: new_image['Id'] for tag in tags})
        try:
            return self[full_name]
        except KeyError:
            raise KeyError("Image not found.", full_name)


class CachedContainerNames(CachedItems, set):
    def refresh(self):
        """
        Fetches all current container names from the client.
        """
        if not self._client:
            return
        current_containers = self._client.containers(all=True)
        self.clear()
        for container in current_containers:
            container_names = container.get('Names')
            if container_names:
                self.update(name[1:] for name in container_names)


class DockerHostItemCache(dict):
    """
    Abstract class for implementing caches of items (containers, images) present on the Docker client, so that
    their existence does not have to be checked separately for every action.

    :param clients: Dictionary of clients with alias and client object.
    :type clients: dict[unicode | str, dockermap.map.config.ClientConfiguration]
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
