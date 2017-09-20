# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
import six
from six.moves import map, filter

from ...functional import resolve_value
from ...shortcuts import chown, chmod
from ...utils import merge_list
from ..input import HostVolume, UsedVolume
from ..policy.utils import get_shared_volume_path


def update_kwargs(kwargs, *updates):
    """
    Utility function for merging multiple keyword arguments, depending on their type:

    * Non-existent keys are added.
    * Existing lists or tuples are extended, but not duplicating entries.
      The keywords ``command`` and ``entrypoint`` are however simply overwritten.
    * Nested dictionaries are updated, overriding previous key-value assignments.
    * Other items are simply overwritten (just like in a regular dictionary update) unless the updating value is
      ``None``.

    Lists/tuples and dictionaries are (shallow-)copied before adding and late resolving values are looked up.
    This function does not recurse.

    :param kwargs: Base keyword arguments. This is modified in-place.
    :type kwargs: dict
    :param updates: Dictionaries to update ``kwargs`` with.
    :type updates: tuple[dict]
    """
    for update in updates:
        if not update:
            continue
        for key, val in six.iteritems(update):
            u_item = resolve_value(val)
            if u_item is None:
                continue
            if key in ('command' or 'entrypoint'):
                kwargs[key] = u_item
            elif isinstance(u_item, (tuple, list)):
                kw_item = kwargs.get(key)
                u_list = map(resolve_value, u_item)
                if isinstance(kw_item, list):
                    merge_list(kw_item, u_list)
                elif isinstance(kw_item, tuple):
                    new_list = list(kw_item)
                    merge_list(new_list, u_list)
                    kwargs[key] = new_list
                else:
                    kwargs[key] = list(u_list)
            elif isinstance(u_item, dict):
                kw_item = kwargs.get(key)
                u_dict = {u_k: resolve_value(u_v) for u_k, u_v in six.iteritems(u_item)}
                if isinstance(kw_item, dict):
                    kw_item.update(u_dict)
                else:
                    kwargs[key] = u_dict
            else:
                kwargs[key] = u_item


def get_volumes(container_map, config, default_volume_paths, include_named):
    """
    Generates volume paths for the ``volumes`` argument during container creation.

    :param container_map: Container map.
    :type container_map: dockermap.map.config.main.ContainerMap
    :param config: Container configuration.
    :type config: dockermap.map.config.container.ContainerConfiguration
    :param default_volume_paths: Dictionary with volume aliases and their default paths.
    :type default_volume_paths: dict[unicode | str, unicode | str]
    :param include_named: Whether to include attached and their re-used volumes. This should be done if Docker supports
      named volumes; otherwise volumes are inherited from other containers via ``volumes_from``.
    :type include_named: bool
    :return: List of shared volume mount points.
    :rtype: list[unicode | str]
    """
    def _bind_volume_path(vol):
        if isinstance(vol, HostVolume):
            return resolve_value(vol.path)
        v_path = resolve_value(default_volume_paths.get(vol.name))
        if v_path:
            return v_path
        raise KeyError("No host-volume information found for alias {0}.".format(vol))

    def _attached_volume_path(vol):
        if isinstance(vol, UsedVolume):
            return resolve_value(vol.path)
        v_path = resolve_value(default_volume_paths.get(vol.name))
        if v_path:
            return v_path
        raise KeyError("No volume information found for alias {0}.".format(vol))

    def _used_volume_path(vol):
        if isinstance(vol, UsedVolume):
            return resolve_value(vol.path)
        if container_map.use_attached_parent_name:
            return resolve_value(default_volume_paths.get(vol.name.partition('.')[2]))
        return resolve_value(default_volume_paths.get(vol.name))

    volumes = list(map(resolve_value, config.shares))
    volumes.extend(map(_bind_volume_path, config.binds))
    if include_named:
        volumes.extend(map(_attached_volume_path, config.attaches))
        volumes.extend(filter(None, map(_used_volume_path, config.uses)))
    return volumes


def get_volumes_from(container_map, config_name, config, policy, include_volumes):
    """
    Generates volume paths for the host config ``volumes_from`` argument during container creation.

    :param container_map: Container map.
    :type container_map: dockermap.map.config.main.ContainerMap
    :param config_name: Container configuration name.
    :type config_name: unicode | str
    :param config: Container configuration.
    :type config: dockermap.map.config.container.ContainerConfiguration
    :param policy: Base policy for generating names and determining volumes.
    :type policy: dockermap.map.policy.base.BasePolicy
    :param include_volumes: Whether to include attached and their re-used volumes. This should not be done if Docker
      supports named volumes, because these are included in ``volumes`` with their paths.
    :type include_volumes: bool
    :return: List of shared volume mount points.
    :rtype: list[unicode | str]
    """
    aname = policy.aname
    cname = policy.cname
    map_name = container_map.name
    volume_names = set(policy.default_volume_paths[map_name].keys())

    def container_name(u_name):
        uc_name, __, ui_name = u_name.partition('.')
        return cname(map_name, uc_name, ui_name)

    def volume_or_container_name(u_name):
        if u_name in volume_names:
            if container_map.use_attached_parent_name:
                v_parent_name, __, attached_name = u_name.partition('.')
                return aname(map_name, attached_name, v_parent_name)
            return aname(map_name, u_name)
        return container_name(u_name)

    def volume_str(name, readonly):
        if readonly:
            return '{0}:ro'.format(name)
        return name

    use_attached_parent_name = container_map.use_attached_parent_name
    if include_volumes:
        volumes_from = [volume_str(volume_or_container_name(u.name), u.readonly)
                        for u in config.uses]
        a_parent_name = config_name if use_attached_parent_name else None
        volumes_from.extend([aname(map_name, attached.name, a_parent_name)
                             for attached in config.attaches])
        return volumes_from

    if use_attached_parent_name:
        return [volume_str(container_name(u.name), u.readonly)
                for u in config.uses
                if u.name.partition('.')[2] not in volume_names]
    return [volume_str(container_name(u.name), u.readonly)
            for u in config.uses
            if u.name not in volume_names]


def get_host_binds(container_map, config_name, config, instance, policy, named_volumes):
    """
    Generates the list of host volumes and named volumes (where applicable) for the host config ``bind`` argument
    during container creation.

    :param container_map: Container map.
    :type container_map: dockermap.map.config.main.ContainerMap
    :param config: Container configuration.
    :type config: dockermap.map.config.container.ContainerConfiguration
    :param instance: Instance name. Pass ``None`` if not applicable.
    :type instance: unicode | str
    :return: List of shared volumes with host volumes and the read-only flag.
    :rtype: list[unicode | str]
    """
    def volume_str(paths, readonly):
        return '{0[1]}:{0[0]}:{1}'.format(paths, 'ro' if readonly else 'rw')

    def _attached_volume(vol):
        parent_name = config_name if use_attached_parent_name else None
        volume_name = aname(map_name, vol.name, parent_name=parent_name)
        if isinstance(vol, UsedVolume):
            path = resolve_value(vol.path)
        else:
            path = resolve_value(default_paths.get(vol.name))
        return volume_str((path, volume_name), vol.readonly)

    def _used_volume(vol):
        if use_attached_parent_name:
            parent_name, __, alias = vol.name.partition('.')
        else:
            alias = vol.name
            parent_name = None
        if alias not in default_paths:
            return None
        volume_name = aname(map_name, alias, parent_name=parent_name)
        if isinstance(vol, UsedVolume):
            path = resolve_value(vol.path)
        else:
            path = resolve_value(default_paths[alias])
        return volume_str((path, volume_name), vol.readonly)

    aname = policy.aname
    map_name = container_map.name
    use_attached_parent_name = container_map.use_attached_parent_name
    default_paths = policy.default_volume_paths[map_name]
    bind = [volume_str(get_shared_volume_path(container_map, shared_volume, instance), shared_volume.readonly)
            for shared_volume in config.binds]
    if named_volumes:
        bind.extend(map(_attached_volume, config.attaches))
        bind.extend(filter(None, map(_used_volume, config.uses)))
    return bind


def _get_ex_port(port_binding):
    return resolve_value(port_binding.exposed_port)


def _get_port_bindings(ex_group, interfaces_ipv4, interfaces_ipv6):
    for port_binding in ex_group:
        bind_port = resolve_value(port_binding.host_port)
        interface = resolve_value(port_binding.interface)
        ipv6 = resolve_value(port_binding.ipv6)
        if interface and bind_port:
            if ipv6:
                bind_addr = resolve_value(interfaces_ipv6.get(interface))
            else:
                bind_addr = resolve_value(interfaces_ipv4.get(interface))
            if not bind_addr:
                raise ValueError("Address for interface '{0}' not found in client configuration.".format(interface))
            yield (bind_addr, bind_port)
        elif bind_port:
            yield bind_port


def get_port_bindings(container_config, client_config):
    """
    Generates the input dictionary contents for the ``port_bindings`` argument.

    :param container_config: Container configuration.
    :type container_config: dockermap.map.config.container.ContainerConfiguration
    :param client_config: Client configuration.
    :type client_config: dockermap.map.config.client.ClientConfiguration
    :return: Dictionary of ports with mapped port, and if applicable, with bind address
    :rtype: dict[unicode | str, list[unicode | str | int | tuple]]
    """
    port_bindings = {}
    if_ipv4 = client_config.interfaces
    if_ipv6 = client_config.interfaces_ipv6
    for exposed_port, ex_port_bindings in itertools.groupby(
            sorted(container_config.exposes, key=_get_ex_port), _get_ex_port):
        bind_list = list(_get_port_bindings(ex_port_bindings, if_ipv4, if_ipv6))
        if bind_list:
            port_bindings[exposed_port] = bind_list
    return port_bindings


def get_preparation_cmd(user, permissions, path):
    """
    Generates the command lines for adjusting a volume's ownership and permission flags. Returns an empty list if there
    is nothing to adjust.

    :param user: User to set ownership for on the path via ``chown``.
    :type user: unicode | str | int | dockermap.functional.AbstractLazyObject
    :param permissions: Permission flags to set via ``chmod``.
    :type permissions: unicode | str | dockermap.functional.AbstractLazyObject
    :param path: Path to adjust permissions on.
    :type path: unicode | str
    :return: Iterator over resulting command strings.
    :rtype: collections.Iterable[unicode | str]
    """
    r_user = resolve_value(user)
    r_permissions = resolve_value(permissions)
    if user:
        yield chown(r_user, path)
    if permissions:
        yield chmod(r_permissions, path)
