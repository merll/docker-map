# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import Counter, defaultdict
import itertools
from operator import itemgetter

import six

from . import DictMap
from .config import ContainerConfiguration, HostVolumeConfiguration
from .input import get_list


SINGLE_ATTRIBUTES = 'repository', 'default_domain', 'set_hostname', 'use_attached_parent_name', 'default_tag'
DICT_ATTRIBUTES = 'volumes', 'host'
LIST_ATTRIBUTES = 'clients',

get_map_config = itemgetter(0, 1)


class MapIntegrityError(Exception):
    """
    Exception for cases where the configurations are not consistent (e.g. a volume alias is missing on the map).
    """
    @property
    def message(self):
        if self.args:
            return self.args[0]
        return None


class ContainerMap(object):
    """
    Class for merging container configurations, host shared volumes and volume alias names.

    :param name: Name for this container map.
    :type name: unicode | str
    :param initial: Initial container configurations, host shares, and volumes.
    :type initial: dict
    :param check_integrity: If initial values are given, the container integrity is checked by default at the end of
     this constructor. Setting this to `False` deactivates it.
    :type check_integrity: bool
    :param check_duplicates: Check for duplicate attached volumes during integrity check.
    :type check_duplicates: bool
    :param kwargs: Kwargs with initial container configurations, host shares, and volumes.
    """
    def __init__(self, name, initial=None, check_integrity=True, check_duplicates=True, **kwargs):
        self._name = name
        self._repository = None
        self._host = HostVolumeConfiguration()
        self._volumes = DictMap()
        self._containers = defaultdict(ContainerConfiguration)
        self._clients = []
        self._default_domain = None
        self._set_hostname = True
        self._use_attached_parent_name = False
        self._default_tag = 'latest'
        self._extended = False
        self.update(initial, **kwargs)
        if self._containers and check_integrity:
            self.check_integrity(check_duplicates=check_duplicates)

    def __iter__(self):
        return ((c_name, c_config) for c_name, c_config in six.iteritems(self._containers) if not c_config.abstract)

    @classmethod
    def _copy_base(cls, from_obj, to_obj):
        """
        :type from_obj: ContainerMap
        :type to_obj: ContainerMap
        """
        for attr in SINGLE_ATTRIBUTES:
            setattr(to_obj, attr, getattr(from_obj, attr))
        for attr in DICT_ATTRIBUTES:
            getattr(to_obj, attr).update(getattr(from_obj, attr))
        for attr in LIST_ATTRIBUTES:
            setattr(to_obj, attr, getattr(from_obj, attr)[:])

    def _update_from_dict(self, items):
        """
        :type items: dict
        """
        for key, value in six.iteritems(items):
            if key == 'host_root':
                self._host.root = value
            elif key in SINGLE_ATTRIBUTES:
                setattr(self, key, value)
            elif key in LIST_ATTRIBUTES:
                setattr(self, key, get_list(value))
            elif key in DICT_ATTRIBUTES:
                getattr(self, key).update(value)
            else:
                if key == 'containers':
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
            if not value:
                continue
            if key == 'host_root':
                if not lists_only:
                    self._host.root = value
            elif key in SINGLE_ATTRIBUTES:
                if not lists_only:
                    setattr(self, key, value)
            elif key in LIST_ATTRIBUTES:
                current_list = getattr(self, key)
                updated_list = get_list(value)
                current_list.extend(u for u in updated_list if u not in current_list)
            elif key in DICT_ATTRIBUTES:
                current_dict = getattr(self, key)
                current_dict.update(value)
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
        self.__class__._copy_base(items, self)
        for container, config in six.iteritems(items._containers):
            self._containers[container].update(config)

    def _merge_from_obj(self, items, lists_only):
        """
        :type items: ContainerMap
        :type lists_only: bool
        """
        for attr in LIST_ATTRIBUTES:
            update_list = getattr(items, attr)
            current_list = getattr(self, attr)
            current_list.extend(c for c in update_list if c not in current_list)
        for attr in DICT_ATTRIBUTES:
            current_dict = getattr(self, attr)
            current_dict.update(getattr(items, attr))
        if not lists_only:
            for attr in SINGLE_ATTRIBUTES:
                setattr(self, attr, getattr(items, attr))
        for container, config in six.iteritems(items._containers):
            if container in self._containers:
                self._containers[container].merge(config, lists_only)
            else:
                self._containers[container].update(config)

    def get_persistent_items(self):
        """
        Returns attached container items and container configurations that are marked as persistent. Each returned
        item is in the format ``(config name, instance/attached name)``, where the instance name can also be ``None``.

        :return: Lists of attached items.
        :rtype: (list[(unicode | str, unicode | str)], list[unicode | str, unicode | str | NoneType])
        """
        attached_items = [(container, ac)
                          for container, config in self
                          for ac in config.attaches]
        persistent_containers = [(container, ci)
                                 for container, config in self if config.persistent
                                 for ci in config.instances or [None]]
        return attached_items, persistent_containers

    @property
    def name(self):
        """
        Container map name.

        :return: Container map name.
        :rtype: unicode | str
        """
        return self._name

    @property
    def clients(self):
        """
        Alias names of clients associated with this container map.

        :return: Client names.
        :rtype: list[unicode | str]
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
        :rtype: dict[unicode | str, dockermap.map.config.ContainerConfiguration]
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
        :rtype: unicode | str
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
        :rtype: unicode | str
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
    def use_attached_parent_name(self):
        """
        Whether to include the parent name of an attached volume in the attached container name for disambiguation.

        :return: When set to ``True``, prefixes each attached volume with the parent name.
        :rtype: bool
        """
        return self._use_attached_parent_name

    @use_attached_parent_name.setter
    def use_attached_parent_name(self, value):
        self._use_attached_parent_name = value

    @property
    def default_tag(self):
        """
        Default tag to use for images where it is not specified. Default is ``latest``.
        """
        return self._default_tag

    @default_tag.setter
    def default_tag(self, value):
        self._default_tag = value

    def dependency_items(self, reverse=False):
        """
        Generates all containers' dependencies, i.e. an iterator on tuples in the format
        ``(container_name, used_containers)``, whereas the used containers are a set, and can be empty.

        :return: Container dependencies.
        :rtype: iterator
        """
        def _get_used_item_np(u):
            v = u.volume
            c, __, i = v.partition('.')
            a = attached.get(c)
            if a:
                return self._name, a, None
            return self._name, c, i or None

        def _get_used_item_ap(u):
            v = u.volume
            c, __, i = v.partition('.')
            a = ext_map.get_existing(c)
            if i in a.attaches:
                return self._name, c, None
            return self._name, c, i or None

        def _get_linked_item(l):
            c, __, i = l.container.partition('.')
            if i:
                return self._name, c, i
            return self._name, c, None

        if self._extended:
            ext_map = self
        else:
            ext_map = self.get_extended_map()

        if not self._use_attached_parent_name:
            attached = {attaches: c_name
                        for c_name, c_config in ext_map
                        for attaches in c_config.attaches}
            used_func = _get_used_item_np
        else:
            used_func = _get_used_item_ap

        def _get_dep_set(config):
            used_set = set(map(used_func, config.uses))
            linked_set = set(map(_get_linked_item, config.links))
            d_set = used_set | linked_set
            nw = config.network
            if isinstance(nw, tuple):
                d_set.add((self._name, ) + nw)
            return d_set

        def _get_grouped_instances(d_map_config, d_instances):
            d_map_name, d_config_name = d_map_config
            d_config = ext_map.get_existing(d_config_name)
            if not d_config:
                raise KeyError("Dependency {0}.{1} for {2}.{3} not found.".format(
                               d_map_name, d_config_name, self._name, c_name))
            if d_config.instances and (None in d_instances or len(d_instances) == len(d_config.instances)):
                return d_map_name, d_config_name, (None, )
            return d_map_name, d_config_name, d_instances

        if reverse:
            # Consolidate dependents.
            for c_name, c_config in ext_map:
                dep_set = set(map(get_map_config, _get_dep_set(c_config)))
                yield (self._name, c_name, (None, )), dep_set
        else:
            # Group instances, or replace with None where all of them are used.
            for c_name, c_config in ext_map:
                dep_set = _get_dep_set(c_config)
                instance_set = set(_get_grouped_instances(map_config, tuple(di[2] for di in items))
                                   for map_config, items in itertools.groupby(sorted(dep_set, key=get_map_config),
                                                                              get_map_config))
                yield (self._name, c_name), instance_set

    def get(self, item):
        """
        Returns a container configuration from the map; if it does not yet exist, an initial config is created and
        returned (to avoid this, use :meth:`get_existing` instead). `item` can be any valid Docker container name.

        :param item: Container name.
        :type item: unicode | str
        :return: A container configuration.
        :rtype: ContainerConfiguration
        """
        return self._containers[item]

    def get_existing(self, item):
        """
        Same as :meth:`get`, except for that non-existing container configurations will not be created; ``None`` is
        returned instead in this case.

        :param item: Container name.
        :type item: unicode | str
        :return: A container configuration
        :rtype: ContainerConfiguration
        """
        return self._containers.get(item)

    def get_extended(self, config):
        """
        Generates a configuration that includes all inherited values.

        :param config: Container configuration.
        :type config: ContainerConfiguration
        :return: A merged (shallow) copy of all inherited configurations merged with the container configuration.
        :rtype: ContainerConfiguration
        """
        if not config.extends or self._extended:
            return config
        extended_config = ContainerConfiguration()
        for ext_name in config.extends:
            ext_cfg_base = self._containers.get(ext_name)
            if not ext_cfg_base:
                raise KeyError(ext_name)
            ext_cfg = self.get_extended(ext_cfg_base)
            extended_config.merge(ext_cfg)
        extended_config.merge(config)
        return extended_config

    def get_extended_map(self):
        """
        Creates a copy of this map which includes all non-abstract configurations in their extended form.

        :return: Copy of this map.
        :rtype: ContainerMap
        """
        map_copy = self.__class__(self.name)
        self.__class__._copy_base(self, map_copy)
        for c_name, c_config in self:
            map_copy.containers[c_name] = self.get_extended(c_config)
        map_copy._extended = True
        return map_copy

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
        * every container referred to in `links` needs to be defined;
        * every container named in `extended` is available.

        :param check_duplicates: Check for duplicate attached volumes.
        :type check_duplicates: bool
        """
        def _get_instance_names(c_name, instances):
            if instances:
                return ['{0}.{1}'.format(c_name, instance) for instance in instances]
            return [c_name]

        def _get_container_items(c_name, c_config):
            instance_names = _get_instance_names(c_name, c_config.instances)
            shared = instance_names[:] if c_config.shares or c_config.binds or c_config.uses else []
            bind = [b.volume for b in c_config.binds if not isinstance(b.volume, tuple)]
            link = [l.container for l in c_config.links]
            uses = [u.volume for u in c_config.uses]
            if isinstance(c_config.network, tuple):
                if c_config.network[1]:
                    network = '{0}.{1}'.format(*c_config.network)
                else:
                    network = c_config.network[0]
            else:
                network = None
            if self._use_attached_parent_name:
                attaches = [(c_name, a) for a in c_config.attaches]
            else:
                attaches = c_config.attaches
            return instance_names, uses, attaches, shared, bind, link, network

        all_instances, all_used, all_attached, all_shared, all_binds, all_links, all_networks = zip(*[
            _get_container_items(k, v) for k, v in self.get_extended_map()
        ])
        if self._use_attached_parent_name:
            all_attached_names = tuple('{0}.{1}'.format(c_name, a)
                                       for c_name, a in itertools.chain.from_iterable(all_attached))
        else:
            all_attached_names = tuple(itertools.chain.from_iterable(all_attached))
        volume_shared = tuple(itertools.chain.from_iterable(all_shared)) + all_attached_names
        if check_duplicates:
            duplicated = [name for name, count in six.iteritems(Counter(volume_shared)) if count > 1]
            if duplicated:
                dup_str = ', '.join(duplicated)
                raise MapIntegrityError("Duplicated attached volumes found with name(s): {0}.".format(dup_str))
        used_set = set(itertools.chain.from_iterable(all_used))
        shared_set = set(volume_shared)
        missing_shares = used_set - shared_set
        if missing_shares:
            missing_share_str = ', '.join(missing_shares)
            raise MapIntegrityError("No shared or attached volumes found for used volume(s): {0}.".format(missing_share_str))
        binds_set = set(itertools.chain.from_iterable(all_binds))
        host_set = set(self._host.keys())
        missing_binds = binds_set - host_set
        if missing_binds:
            missing_mapped_str = ', '.join(missing_binds)
            raise MapIntegrityError("No host share found for mapped volume(s): {0}.".format(missing_mapped_str))
        if self._use_attached_parent_name:
            volume_set = binds_set.union(a[1] for a in itertools.chain.from_iterable(all_attached))
        else:
            volume_set = binds_set.union(all_attached_names)
        named_set = set(self._volumes.keys())
        missing_names = volume_set - named_set
        if missing_names:
            missing_names_str = ', '.join(missing_names)
            raise MapIntegrityError("No volume name-path-assignments found for volume(s): {0}.".format(missing_names_str))
        instance_set = set(itertools.chain.from_iterable(all_instances))
        linked_set = set(itertools.chain.from_iterable(all_links))
        missing_links = linked_set - instance_set
        if missing_links:
            missing_links_str = ', '.join(missing_links)
            raise MapIntegrityError("No container instance found for link(s): {0}.".format(missing_links_str))
        network_set = set(filter(None, all_networks))
        missing_networks = network_set - instance_set
        if missing_networks:
            missing_networks_str = ', '.join(missing_networks)
            raise MapIntegrityError("No container instance found for the following network reference(s): {0}".format(missing_networks_str))
