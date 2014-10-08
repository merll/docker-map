# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import Counter, defaultdict
import itertools
import six

from . import DictMap
from .config import ContainerConfiguration, HostVolumeConfiguration
from .dep import MultiDependencyResolver


class ContainerDependencyResolver(MultiDependencyResolver):
    """
    Resolves dependencies between :class:`dockermap.map.config.ContainerConfiguration` instances, based on shared and
    used volumes.

    :param container_map: Optional :class:`ContainerMap` instance for initialization.
    :type container_map: ContainerMap
    """
    def __init__(self, container_map=None):
        items = container_map.dependency_items if container_map else None
        super(ContainerDependencyResolver, self).__init__(items)

    def merge_dependency(self, item, resolve_parent, parents):
        """
        Merge dependencies of current container with further dependencies; in this instance, it means that first parent
        dependencies are checked, and then immediate dependencies of the current container should be added to the list,
        but without duplicating any entries.

        :param item: Container name.
        :type item: unicode
        :param resolve_parent: Function to resolve parent dependencies.
        :type resolve_parent: __builtin__.function
        :type parents: iterable
        :return: List of recursively resolved dependencies of this container.
        :rtype: list
        """
        dep = list(parents)
        for parent in parents:
            parent_dep = resolve_parent(parent)
            if parent_dep:
                dep.extend(set(parent_dep).difference(dep))
        return dep

    def update(self, container_map):
        """
        Overrides the `update` function of the superclass to use a :class:`ContainerMap` instance.

        :param container_map: :class:`ContainerMap` instance
        :type container_map: ContainerMap
        """
        super(ContainerDependencyResolver, self).update(container_map.dependency_items)

    def update_backward(self, container_map):
        """
        Overrides the `update_backward` function of the superclass to use a :class:`ContainerMap` instance.

        :param container_map: :class:`ContainerMap` instance
        :type container_map: ContainerMap
        """
        super(ContainerDependencyResolver, self).update_backward(container_map.dependency_items)


class ContainerMap(object):
    """
    Class for merging container configurations, host shared volumes and volume alias names.

    :param name: Name for this container map.
    :type name: unicode
    :param initial: Initial container configurations, host shares, and volumes.
    :type initial: dict
    :param check_integrity: If initial values are given, the container integrity is checked by default at the end of
     this constructor. Setting this to `False` deactivates it.
    :type check_integrity: bool
    :param kwargs: Kwargs with initial container configurations, host shares, and volumes.
    """
    def __init__(self, name, initial=None, check_integrity=True, **kwargs):
        self._name = name
        self._repository = None
        self._host = HostVolumeConfiguration()
        self._volumes = DictMap()
        self._containers = defaultdict(ContainerConfiguration)
        self.update(initial, **kwargs)
        if (initial or kwargs) and check_integrity:
            self.check_integrity()

    def __iter__(self):
        return six.iteritems(self._containers)

    @property
    def name(self):
        """
        Container map name.

        :return: Container map name.
        :rtype: unicode
        """
        return self._name

    @property
    def containers(self):
        """
        Container configurations of the map.

        :return: Container configurations.
        :rtype: dict
        """
        return self._containers

    @property
    def volumes(self):
        """
        Volume alias assignments of the map.

        :return: Volume alias assignments.
        :rtype: DictMap
        """
        return self._volumes

    @property
    def host(self):
        """
        Host volume configuration of the map.

        :return: Host volume configuration.
        :rtype: HostVolumeConfiguration
        """
        return self._host

    @property
    def repository(self):
        """
        Repository prefix for images. This is prepended to image names used by container configurations.

        :return: Repository prefix.
        :rtype: unicode
        """
        return self._repository

    @repository.setter
    def repository(self, value):
        self._repository = value

    @property
    def dependency_items(self):
        """
        Generates all containers' dependencies, i.e.. an iterator on tuples in the format
        ``(container_name, used_containers)``, whereas the used containers are a set, and can be empty.

        :return: Container dependencies.
        :rtype: iterator
        """
        attached = dict((attaches, c_name) for c_name, c_config in self for attaches in c_config.attaches)
        for c_name, c_config in self:
            dep_set = set(attached.get(u, u) for u in c_config.uses).union(l.container for l in c_config.links)
            for i in c_config.instances:
                yield '.'.join((c_name, i)), dep_set
            yield c_name, dep_set

    def cname(self, container, instance=None):
        """
        Formats the instantiated container's name. For containers with several instances, the format is
        `map_name.container_name.instance_name`; for others, it is just `map_name.container_name`.

        :param container: Container name.
        :param instance: Optional instance name.
        :return: Docker container name.
        :rtype: unicode
        """
        if instance:
            return '.'.join((self._name, container, instance))
        return '.'.join((self._name, container))

    def iname(self, image):
        """
        Formats an image name for a container configuration. If the repository prefix is already part of that name, it
        is not modified.
        Otherwise the image name is prefixed with the default :attr:`repository`.

        :param image: Image name.
        :type image: unicode
        :return: Repository-image name.
        """
        if '/' in image:
            if image[0] == '/':
                return image[1:]
            return image
        return '/'.join((self._repository, image))

    def get(self, item):
        """
        Returns a container configuration from the map; if it does not yet exist, an initial config is created and
        returned (to avoid this, use :func:`get_existing` instead). `item` can be any valid Docker container name.

        :param item: Container name.
        :type item: unicode
        :return: A container configuration.
        :rtype: ContainerConfiguration
        """
        return self._containers[item]

    def get_existing(self, item):
        """
        Same as :func:`get`, except for that non-existing container configurations will not be created; `None` is
        returned instead in this case.

        :param item: Container name.
        :type item: unicode
        :return: A container configuration
        :rtype: ContainerConfiguration
        """
        return self._containers.get(item)

    def update(self, other=None, **kwargs):
        """
        Updates the container map with a dictionary. The keys need to be container names, the values should be a
        dictionary structure of :class:`dockermap.map.config.ContainerConfiguration` properties. `host` and `volumes`
        can also be included.

        :item other: Dictionary to update the map with.
        :type other: dict
        :param kwargs: Kwargs to update the map with
        """
        def _update(items):
            for key, value in six.iteritems(items):
                if key == 'volumes':
                    self._volumes.update(value)
                elif key == 'host':
                    self._host.update(value)
                elif key == 'host_root':
                    self._host.root = value
                elif key == 'repository':
                    self._repository = value
                elif key == 'containers':
                    for container, config in six.iteritems(value):
                        self._containers[container].update(config)
                else:
                    self._containers[key].update(value)

        if isinstance(other, dict):
            _update(other)
        _update(kwargs)

    def check_integrity(self, check_duplicates=True):
        """
        Checks the integrity of the container map. This means, that
        * every shared container (instance name) and attached volume should only exist once (can be deactivated);
        * every container declared as `used` needs to have at least a shared volume or a host bind;
        * every host bind declared under `binds` needs to be shared from the host;
        * every volume alias used in `attached` and `binds` needs to be associated with a path in `volumes`;
        * every container referred to in `links` needs to be defined.

        :param: Check for duplicate attached volumes.
        :type check_duplicates: bool
        """
        def _get_instance_names(c_name, instances):
            if instances:
                return ['.'.join((c_name, instance)) for instance in instances]
            else:
                return [c_name]

        def _get_container_items(c_name, container):
            instance_names = _get_instance_names(c_name, container.instances)
            shared = instance_names[:] if container.shares or container.binds else []
            bind = [b.volume for b in container.binds]
            link = [l.container for l in container.links]
            return instance_names, container.uses, container.attaches, shared, bind, link

        all_instances, all_used, all_attached, all_shared, all_binds, all_links = zip(*[_get_container_items(k, v) for k, v in self])
        volume_shared = tuple(itertools.chain.from_iterable(all_shared + all_attached))
        if check_duplicates:
            duplicated = [name for name, count in six.iteritems(Counter(volume_shared)) if count > 1]
            if duplicated:
                dup_str = ', '.join(duplicated)
                raise ValueError("Duplicated shared or attached volumes found with name(s): {0}.".format(dup_str))
        used_set = set(itertools.chain.from_iterable(all_used))
        shared_set = set(volume_shared)
        missing_shares = used_set - shared_set
        if missing_shares:
            missing_share_str = ', '.join(missing_shares)
            raise ValueError("No shared or attached volumes found for used volume(s): {0}.".format(missing_share_str))
        binds_set = set(itertools.chain.from_iterable(all_binds))
        host_set = set(self._host.keys())
        missing_binds = binds_set - host_set
        if missing_binds:
            missing_mapped_str = ', '.join(missing_binds)
            raise ValueError("No host share found for mapped volume(s): {0}.".format(missing_mapped_str))
        volume_set = binds_set.union(itertools.chain.from_iterable(all_attached))
        named_set = set(self._volumes.keys())
        missing_names = volume_set - named_set
        if missing_names:
            missing_names_str = ', '.join(missing_names)
            raise ValueError("No volume name-path-assignments found for volume(s): {0}.".format(missing_names_str))
        instance_set = set(itertools.chain.from_iterable(all_instances))
        linked_set = set(itertools.chain.from_iterable(all_links))
        missing_links = linked_set - instance_set
        if missing_links:
            missing_links_str = ', '.join(missing_links)
            raise ValueError("No container instance found for link(s): {0}.".format(missing_links_str))
