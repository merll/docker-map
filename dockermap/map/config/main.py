# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import Counter
import itertools

import six
from six.moves import map, zip

from ... import DEFAULT_PRESET_NETWORKS
from ...functional import resolve_value
from ...utils import merge_list
from .. import DictMap, DefaultDictMap
from ..input import ItemType, bool_if_set, MapConfigId, SharedVolume, UsedVolume
from ..exceptions import MapIntegrityError
from . import ConfigurationObject, CP
from .container import ContainerConfiguration
from .host_volume import HostVolumeConfiguration
from .network import NetworkConfiguration
from .volume import VolumeConfigurationMap


class ContainerMap(ConfigurationObject):
    """
    Class for merging container configurations, host shared volumes, and volume alias names.

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
    repository = CP()
    host = CP(dict, default=HostVolumeConfiguration, input_func=HostVolumeConfiguration, update=False)
    clients = CP(list)
    groups = CP(dict, default=DictMap, input_func=DictMap)
    default_domain = CP()
    set_hostname = CP(default=True, input_func=bool_if_set)
    use_attached_parent_name = CP(default=False, input_func=bool_if_set)
    default_tag = CP(default='latest')

    DOCSTRINGS = {
        'repository': "Repository prefix for images. This is prepended to image names used by container "
                      "configurations.",
        'host': "Volume alias assignments of the map.",
        'clients': "Alias names of clients associated with this container map.",
        'groups': "Groups of configured containers.",
        'default_domain': "Value to use as domain name for new containers, unless the client specifies otherwise.",
        'set_hostname': "Whether to set the hostname for new containers. When set to ``False``, uses Docker's default "
                        "autogeneration of hostnames instead.",
        'use_attached_parent_name': "Whether to include the parent name of an attached volume in the attached "
                                    "container name for disambiguation.",
        'default_tag': "Default tag to use for images where it is not specified. Default is ``latest``.",
    }

    def __init__(self, name, initial=None, check_integrity=True, check_duplicates=True, **kwargs):
        self._name = name
        self._extended = False
        self._containers = containers = DefaultDictMap(ContainerConfiguration)
        self._volumes = VolumeConfigurationMap()
        self._networks = DefaultDictMap(NetworkConfiguration)
        super(ContainerMap, self).__init__(initial, **kwargs)
        if containers and check_integrity:
            self.check_integrity(check_duplicates=check_duplicates)

    def __iter__(self):
        return ((c_name, c_config) for c_name, c_config in six.iteritems(self._containers) if not c_config.abstract)

    def update_default_from_dict(self, key, value):
        if key == 'containers':
            items = self._containers
        elif key == 'networks':
            items = self._networks
        elif key == 'volumes':
            items = self._volumes
        else:
            items = None
        if items is not None:
            for s_key, s_value in six.iteritems(value):
                items[s_key].update_from_dict(s_value)
        elif key == 'host_root':
            self.host.root = value
        else:
            self._containers[key].update_from_dict(value)

    def merge_default_from_dict(self, key, value, lists_only=False):
        if key == 'containers':
            items = self._containers
        elif key == 'networks':
            items = self._networks
        elif key == 'volumes':
            items = self._volumes
        else:
            items = None
        if items is not None:
            for s_key, s_value in six.iteritems(value):
                if s_key in items:
                    items[s_key].merge_from_dict(s_value, lists_only=lists_only)
                else:
                    items[s_key].update_from_dict(s_value)
        elif key == 'host_root':
            if not lists_only:
                self.host.root = value
        elif key in self._containers:
            self._containers[key].merge_from_dict(value, lists_only=lists_only)
        else:
            self._containers[key].update_from_dict(value)

    def update_from_dict(self, dct):
        host = dct.get('host')
        if host:
            self._config['host'] = HostVolumeConfiguration(host)
        containers = dct.get('containers')
        if containers:
            self._config['containers'] = c_containers = DefaultDictMap(ContainerConfiguration)
            c_containers.update(containers)
        networks = dct.get('networks')
        if networks:
            self._config['networks'] = c_networks = DefaultDictMap(NetworkConfiguration)
            c_networks.update(networks)
        volumes = dct.get('volumes')
        if volumes:
            self._config['volumes'] = c_volumes = VolumeConfigurationMap()
            c_volumes.update(volumes)
        super(ContainerMap, self).update_from_dict(dct)

    def update_from_obj(self, obj, copy=False, update_containers=True):
        self._config['host'] = obj.host.copy() if copy else obj.host
        if update_containers:
            for key, value in obj.containers:
                self._containers[key].update_from_obj(value, copy=copy)
        for update_items, current_items in zip(
            [obj.networks, obj.volumes],
            [self._networks, self._volumes]
        ):
            for key, value in update_items:
                current_items[key].update_from_obj(value, copy=copy)
        super(ContainerMap, self).update_from_obj(obj, copy=copy)

    def merge_from_obj(self, obj, lists_only=False):
        for update_items, current_items in zip(
            [obj.containers, obj.networks, obj.volumes],
            [self._containers, self._networks, self._volumes]
        ):
            for key, value in update_items:
                if key in current_items:
                    current_items[key].merge_from_obj(value, lists_only=lists_only)
                else:
                    current_items[key].update_from_obj(value)
        super(ContainerMap, self).merge_from_obj(obj, lists_only=lists_only)

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
    def containers(self):
        """
        Container configurations of the map.

        :return: Container configurations.
        :rtype: dict[unicode | str, dockermap.map.config.container.ContainerConfiguration]
        """
        return self._containers

    @containers.setter
    def containers(self, value):
        if isinstance(value, DefaultDictMap) and value.default_factory is ContainerConfiguration:
            self._containers = value
        else:
            self._containers.clear()
            self._containers.update(value)

    @property
    def networks(self):
        """
        Network configurations on the map.

        :return: Network configurations.
        :rtype: dict[unicode | str, dockermap.map.config.network.NetworkConfiguration]
        """
        return self._networks

    @networks.setter
    def networks(self, value):
        if isinstance(value, DefaultDictMap) and value.default_factory is NetworkConfiguration:
            self._networks = value
        else:
            self._networks.clear()
            self._networks.update(value)

    @property
    def volumes(self):
        """
        Volume configurations on the map.

        :return: Volume configurations.
        :rtype: dict[unicode | str, dockermap.map.config.volume.VolumeConfiguration]
        """
        return self._volumes

    @volumes.setter
    def volumes(self, value):
        if isinstance(value, VolumeConfigurationMap):
            self._volumes = value
        else:
            self._volumes.clear()
            self._volumes.update(value)

    def get_image(self, image):
        """
        Generates a tuple of the full image name and tag, that should be used when creating a new container.

        This implementation applies the following rules:

        * If the image name starts with ``/``, the following image name is returned.
        * If ``/`` is found anywhere else in the image name, it is assumed to be a repository-prefixed image and
          returned as it is.
        * Otherwise, if the given container map has a repository prefix set, this is prepended to the image name.
        * In any other case, the image name is not modified.

        Where there is a tag included in the ``image`` name, it is not modified. If it is not, the default tag from the
        container map, or ``latest`` is used.

        :param image: Image name.
        :type image: unicode | str
        :return: Image name, where applicable prefixed with a repository, and tag.
        :rtype: (unicode | str, unicode | str)
        """
        name, __, tag = image.rpartition(':')
        if not name:
            name, tag = tag, name
        if '/' in name:
            if name[0] == '/':
                repo_name = name[1:]
            else:
                repo_name = name
        else:
            default_prefix = resolve_value(self.repository)
            if default_prefix:
                repo_name = '{0}/{1}'.format(default_prefix, name)
            else:
                repo_name = name
        if tag:
            return repo_name, tag
        default_tag = resolve_value(self.default_tag)
        return repo_name, default_tag or 'latest'

    def dependency_items(self):
        """
        Generates all containers' dependencies, i.e. an iterator on tuples in the format
        ``(container_name, used_containers)``, whereas the used containers are a set, and can be empty.

        :return: Container dependencies.
        :rtype: collections.Iterable
        """
        def _get_used_items_np(u):
            volume_config_name, __, volume_instance = u.name.partition('.')
            attaching_config_name = attaching.get(volume_config_name)
            if attaching_config_name:
                used_c_name = attaching_config_name
                used_instances = instances.get(attaching_config_name)
            else:
                used_c_name = volume_config_name
                if volume_instance:
                    used_instances = (volume_instance, )
                else:
                    used_instances = instances.get(volume_config_name)
            return [MapConfigId(ItemType.CONTAINER, self._name, used_c_name, ai)
                    for ai in used_instances or (None, )]

        def _get_used_items_ap(u):
            volume_config_name, __, volume_instance = u.name.partition('.')
            attaching_config = ext_map.get_existing(volume_config_name)
            attaching_instances = instances.get(volume_config_name)
            config_volumes = {a.name for a in attaching_config.attaches}
            if not volume_instance or volume_instance in config_volumes:
                used_instances = attaching_instances
            else:
                used_instances = (volume_instance, )
            return [MapConfigId(ItemType.CONTAINER, self._name, volume_config_name, ai)
                    for ai in used_instances or (None, )]

        def _get_linked_items(lc):
            linked_config_name, __, linked_instance = lc.partition('.')
            if linked_instance:
                linked_instances = (linked_instance, )
            else:
                linked_instances = instances.get(linked_config_name)
            return [MapConfigId(ItemType.CONTAINER, self._name, linked_config_name, li)
                    for li in linked_instances or (None, )]

        def _get_network_mode_items(n):
            net_config_name, net_instance = n
            network_ref_config = ext_map.get_existing(net_config_name)
            if network_ref_config:
                if net_instance and net_instance in network_ref_config.instances:
                    network_instances = (net_instance, )
                else:
                    network_instances = network_ref_config.instances or (None, )
                return [MapConfigId(ItemType.CONTAINER, self._name, net_config_name, ni)
                        for ni in network_instances]
            return []

        def _get_network_items(n):
            if n.network_name in DEFAULT_PRESET_NETWORKS:
                return []
            net_items = [MapConfigId(ItemType.NETWORK, self._name, n.network_name)]
            if n.links:
                net_items.extend(itertools.chain.from_iterable(_get_linked_items(l.container) for l in n.links))
            return net_items

        if self._extended:
            ext_map = self
        else:
            ext_map = self.get_extended_map()

        instances = {c_name: c_config.instances
                     for c_name, c_config in ext_map}
        if not self.use_attached_parent_name:
            attaching = {attaches.name: c_name
                         for c_name, c_config in ext_map
                         for attaches in c_config.attaches}
            used_func = _get_used_items_np
        else:
            used_func = _get_used_items_ap

        def _get_dep_list(name, config):
            image, tag = self.get_image(config.image or name)
            d = []
            nw = config.network_mode
            if isinstance(nw, tuple):
                merge_list(d, _get_network_mode_items(nw))
            merge_list(d, itertools.chain.from_iterable(map(_get_network_items, config.networks)))
            merge_list(d, itertools.chain.from_iterable(map(used_func, config.uses)))
            merge_list(d, itertools.chain.from_iterable(_get_linked_items(l.container) for l in config.links))
            d.extend(MapConfigId(ItemType.VOLUME, self._name, name, a.name)
                     for a in config.attaches)
            d.append(MapConfigId(ItemType.IMAGE, self._name, image, tag))
            return d

        for c_name, c_config in ext_map:
            dep_list = _get_dep_list(c_name, c_config)
            for c_instance in c_config.instances or (None, ):
                yield MapConfigId(ItemType.CONTAINER, self._name, c_name, c_instance), dep_list

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

    def get_network(self, name):
        """
        Returns a network configuration from the map; if it does not yet exist, an initial config is created and
        returned (to avoid this, use :meth:`get_existing_network` instead). `name` can be any valid network name.

        :param name: Network name.
        :type name: unicode | str
        :return: A network configuration.
        :rtype: dockermap.map.config.network.NetworkConfiguration
        """
        return self._networks[name]

    def get_volume(self, name):
        """
        Returns a volume configuration from the map; if it does not yet exist, an initial config is created and
        returned (to avoid this, use :meth:`get_existing_volume` instead). `name` can be any valid volume name.

        :param name: Volume alias.
        :type name: unicode | str
        :return: A volume configuration.
        :rtype: dockermap.map.config.volume.VolumeConfiguration
        """
        return self._volumes[name]

    def get_existing_network(self, name):
        """
        Same as :meth:`get_network`, except for that non-existing network configurations will not be created; ``None``
        is returned instead in this case.

        :param name: Network name.
        :type name: unicode | str
        :return: A network configuration.
        :rtype: dockermap.map.config.network.NetworkConfiguration
        """
        return self._networks.get(name)

    def get_existing_volume(self, name):
        """
        Same as :meth:`get_volume`, except for that non-existing volume configurations will not be created; ``None``
        is returned instead in this case.

        :param name: Volume alias.
        :type name: unicode | str
        :return: A volume configuration.
        :rtype: dockermap.map.config.volume.VolumeConfiguration
        """
        return self._volumes.get(name)

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
            extended_config.merge_from_obj(ext_cfg)
        extended_config.merge_from_obj(config)
        return extended_config

    def get_extended_map(self):
        """
        Creates a copy of this map which includes all non-abstract configurations in their extended form.

        :return: Copy of this map.
        :rtype: ContainerMap
        """
        map_copy = self.__class__(self.name)
        map_copy.update_from_obj(self, copy=True, update_containers=False)
        for c_name, c_config in self:
            map_copy._containers[c_name] = self.get_extended(c_config)
        map_copy._extended = True
        return map_copy

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
            group_ref_names = instance_names[:]
            if c_config.instances:
                group_ref_names.append(c_name)
            shared = instance_names[:] if c_config.shares or c_config.binds or c_config.uses else []
            bind = [b.name for b in c_config.binds if isinstance(b, SharedVolume)]
            link = [l.container for l in c_config.links]
            uses = [u.name for u in c_config.uses]
            networks = [n.network_name for n in c_config.networks if n.network_name not in DEFAULT_PRESET_NETWORKS]
            network_mode = c_config.network_mode
            if isinstance(network_mode, tuple):
                if network_mode[1]:
                    net_containers = ['{0[0]}.{0[1]}'.format(network_mode)]
                else:
                    net_containers = [network_mode[0]]
            else:
                net_containers = []
            if self.use_attached_parent_name:
                attaches = [(c_name, a.name) for a in c_config.attaches]
            else:
                attaches = [a.name for a in c_config.attaches]
            attaches_with_path = [a.name for a in c_config.attaches
                                  if isinstance(a, UsedVolume)]
            return (instance_names, group_ref_names, uses, attaches, attaches_with_path, shared, bind, link, networks,
                    net_containers)

        (all_instances, all_grouprefs, all_used, all_attached, all_attached_default, all_shared, all_binds, all_links,
         all_networks, all_net_containers) = zip(*[
            _get_container_items(k, v) for k, v in self.get_extended_map()
         ])
        if self.use_attached_parent_name:
            all_attached_names = tuple('{0}.{1}'.format(c_name, a)
                                       for c_name, a in itertools.chain.from_iterable(all_attached))
        else:
            all_attached_names = tuple(itertools.chain.from_iterable(all_attached))

        ref_set = set(itertools.chain.from_iterable(all_grouprefs))
        group_set = set(self.groups.keys())
        ambiguous_names = group_set & ref_set
        if ambiguous_names:
            ambiguous_str = ', '.join(ambiguous_names)
            raise MapIntegrityError("Names are used both for container configurations (or instances) and for container "
                                    "groups: {0}.".format(ambiguous_str))
        group_referenced = set(itertools.chain.from_iterable(self.groups.values()))
        missing_refs = group_referenced - ref_set
        if missing_refs:
            missing_ref_str = ', '.join(missing_refs)
            raise MapIntegrityError("Container configurations or certain instances are referenced by groups, but are "
                                    "not defined: {0}.".format(missing_ref_str))
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
            raise MapIntegrityError("No shared or attached volumes found for used volume(s): "
                                    "{0}.".format(missing_share_str))
        binds_set = set(itertools.chain.from_iterable(all_binds))
        host_set = set(self.host.keys())
        missing_binds = binds_set - host_set
        if missing_binds:
            missing_mapped_str = ', '.join(missing_binds)
            raise MapIntegrityError("No host share found for mapped volume(s): {0}.".format(missing_mapped_str))
        if self.use_attached_parent_name:
            volume_set = binds_set.union(a[1] for a in itertools.chain.from_iterable(all_attached))
        else:
            volume_set = binds_set.union(all_attached_names)
        named_set = set(self.volumes.keys()).union(itertools.chain.from_iterable(all_attached_default))
        missing_names = volume_set - named_set
        if missing_names:
            missing_names_str = ', '.join(missing_names)
            raise MapIntegrityError("No volume name-path-assignments found for volume(s): "
                                    "{0}.".format(missing_names_str))
        instance_set = set(itertools.chain.from_iterable(all_instances))
        linked_set = set(itertools.chain.from_iterable(all_links))
        missing_links = linked_set - instance_set
        if missing_links:
            missing_links_str = ', '.join(missing_links)
            raise MapIntegrityError("No container instance found for link(s): {0}.".format(missing_links_str))
        used_network_set = set(itertools.chain.from_iterable(all_networks))
        used_net_container_set = set(itertools.chain.from_iterable(all_net_containers))
        available_network_set = set(self.networks.keys())
        missing_networks = used_network_set - available_network_set
        if missing_networks:
            missing_networks_str = ', '.join(missing_networks)
            raise MapIntegrityError("No network configuration found for the following network reference(s): "
                                    "{0}".format(missing_networks_str))
        missing_net_containers = used_net_container_set - instance_set
        if missing_net_containers:
            missing_net_cnt_str = ', '.join(missing_net_containers)
            raise MapIntegrityError("No container instance found for the following network mode reference(s): "
                                    "{0}".format(missing_net_cnt_str))
