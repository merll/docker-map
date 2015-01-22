# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import Counter, defaultdict
import itertools
import six

from . import DictMap
from .config import ContainerConfiguration, HostVolumeConfiguration


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
        self._clients = list()
        self._default_domain = None
        self._set_hostname = True
        self.update(initial, **kwargs)
        if (initial or kwargs) and check_integrity:
            self.check_integrity()

    def __iter__(self):
        return six.iteritems(self._containers)

    def _update_from_dict(self, items):
        """
        :type items: dict
        """
        for key, value in six.iteritems(items):
            if key == 'volumes':
                self._volumes.update(value)
            elif key == 'host':
                self._host.update(value)
            elif key == 'host_root':
                self._host.root = value
            elif key == 'repository':
                self._repository = value
            elif key == 'default_domain':
                self._default_domain = value
            elif key == 'clients':
                self._clients = list(value)
            elif key == 'containers':
                for container, config in six.iteritems(value):
                    self._containers[container].update(config)
            else:
                self._containers[key].update(value)

    def _merge_from_dict(self, items, lists_only):
        """
        :type items: dict
        :type lists_only: bool
        """
        for key, value in six.iteritems(items):
            if key == 'volumes':
                self._volumes.update(value)
            elif key == 'host':
                self._host.update(value)
            elif key == 'host_root':
                if not lists_only:
                    self._host.root = value
            elif key == 'repository':
                if not lists_only:
                    self._repository = value
            elif key == 'default_domain':
                if not lists_only:
                    self._default_domain = value
            elif key == 'set_hostname':
                if not lists_only:
                    self._default_domain = value
            elif key == 'clients':
                self._clients.extend(set(value) - set(self._clients))
            elif key == 'containers':
                for container, config in six.iteritems(value):
                    if container in self._containers:
                        self._containers[container].merge(config, lists_only)
                    else:
                        self._containers[container].update(config)
            else:
                if key in self._containers:
                    self._containers[key].merge(value, lists_only)
                else:
                    self._containers[key].update(value)

    def _update_from_obj(self, items):
        """
        :type items: ContainerMap
        """
        self._volumes.update(items._volumes)
        self._host.update(items._host)
        self._repository = items._repository
        self._clients = items._clients
        self._default_domain = items._default_domain
        self._set_hostname = items._set_hostname
        for container, config in items:
            self._containers[container].update(config)

    def _merge_from_obj(self, items, lists_only):
        """
        :type items: ContainerMap
        :type lists_only: bool
        """
        self._volumes.update(items._volumes)
        self._host.update(items._host)
        self._clients.extend(set(items._clients) - set(self._clients))
        if not lists_only:
            self._repository = items._repository
            self._default_domain = items._default_domain
            self._set_hostname = items._set_hostname
        for container, config in items:
            if container in self._containers:
                self._containers[container].merge(config, lists_only)
            else:
                self._containers[container] = config

    @property
    def name(self):
        """
        Container map name.

        :return: Container map name.
        :rtype: unicode
        """
        return self._name

    @property
    def clients(self):
        """
        Alias names of clients associated with this container map.

        :return: Client names.
        :rtype: list[unicode]
        """
        return self._clients

    @clients.setter
    def clients(self, value):
        self._clients = list(value)

    @property
    def containers(self):
        """
        Container configurations of the map.

        :return: Container configurations.
        :rtype: dict[unicode, dockermap.map.config.ContainerConfiguration]
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
    def default_domain(self):
        """
        Value to use as domain name for new containers, unless the client specifies otherwise.

        :return: Default domain name.
        :rtype: unicode
        """
        return self._default_domain

    @default_domain.setter
    def default_domain(self, value):
        self._default_domain = value

    @property
    def set_hostname(self):
        """
        Whether to set the hostname for new containers.

        :return: When set to ``False``, uses Docker's default autogeneration of hostnames instead.
        :rtype: bool
        """
        return self._set_hostname

    @set_hostname.setter
    def set_hostname(self, value):
        self._set_hostname = value

    @property
    def dependency_items(self):
        """
        Generates all containers' dependencies, i.e. an iterator on tuples in the format
        ``(container_name, used_containers)``, whereas the used containers are a set, and can be empty.

        :return: Container dependencies.
        :rtype: iterator
        """
        def _get_used_item(u):
            c, __, i = u.partition('.')
            if i:
                return self._name, c, i
            return self._name, attached.get(c, c), None

        def _get_linked_item(l):
            c, __, i = l.container.partition('.')
            if i:
                return self._name, c, i
            return self._name, c, None

        attached = dict((attaches, c_name) for c_name, c_config in self for attaches in c_config.attaches)
        for c_name, c_config in self:
            used_set = set(map(_get_used_item, c_config.uses))
            linked_set = set(map(_get_linked_item, c_config.links))
            dep_set = used_set | linked_set
            for c_instance in c_config.instances:
                yield (self._name, c_name, c_instance), dep_set
            yield (self._name, c_name, None), dep_set

    def get(self, item):
        """
        Returns a container configuration from the map; if it does not yet exist, an initial config is created and
        returned (to avoid this, use :meth:`get_existing` instead). `item` can be any valid Docker container name.

        :param item: Container name.
        :type item: unicode
        :return: A container configuration.
        :rtype: ContainerConfiguration
        """
        return self._containers[item]

    def get_existing(self, item):
        """
        Same as :meth:`get`, except for that non-existing container configurations will not be created; ``None`` is
        returned instead in this case.

        :param item: Container name.
        :type item: unicode
        :return: A container configuration
        :rtype: ContainerConfiguration
        """
        return self._containers.get(item)

    def update(self, other=None, **kwargs):
        """
        Updates the container map with a dictionary or another instance. In case of a dictionary, the keys need to be
        container names, the values should be a dictionary structure of
        :class:`dockermap.map.config.ContainerConfiguration` properties. ``host``, ``host_root``, and ``volumes`` can
        also be included.

        :item other: Dictionary or ContainerMap to update the map with.
        :type other: ContainerMap or dict
        :param kwargs: Kwargs to update the map with
        """
        if other:
            if isinstance(other, ContainerMap):
                self._update_from_obj(other)
            elif isinstance(other, dict):
                self._update_from_dict(other)
            else:
                raise ValueError("Expected ContainerMap or dictionary; found '{0}'".format(type(other)))
        self._update_from_dict(kwargs)

    def merge(self, c_map, lists_only=False):
        """
        Merges a container map and its items into the current one.

        :param c_map: Merging dictionary or ContainerMap
        :type c_map: ContainerMap or dict
        :param lists_only: Restrict merge to list-based fields of container configurations. In the default  ``True``
         setting, overwrites existing single-values and updates dictionary attributes.
        """
        if isinstance(c_map, ContainerMap):
            self._merge_from_obj(c_map, lists_only)
        elif isinstance(c_map, dict):
            self._merge_from_dict(c_map, lists_only)
        else:
            raise ValueError("Expected ContainerMap or dictionary; found '{0}'".format(type(c_map)))

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
