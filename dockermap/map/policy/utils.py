# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six
from six.moves import map, filter

from ...functional import resolve_value
from ...utils import merge_list
from ..config.host_volume import get_host_path
from ..input import is_path, HostVolume, UsedVolume, SharedVolume

INITIAL_START_TIME = '0001-01-01T00:00:00Z'


def extract_user(user_value):
    """
    Extract the user for running a container from the following possible input formats:

    * Integer (UID)
    * User name string
    * Tuple of ``user, group``
    * String in the format ``user:group``

    :param user_value: User name, uid, user-group tuple, or user:group string.
    :type user_value: int | tuple | unicode | str
    :return: User name or id.
    :rtype: unicode | str
    """
    user = resolve_value(user_value)
    if not user and user != 0 and user != '0':
        return None
    if isinstance(user, tuple):
        return user[0]
    if isinstance(user, six.integer_types):
        return six.text_type(user)
    return user.partition(':')[0]


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


def init_options(options):
    """
    Initialize ``create_options`` or  ``start_options`` of a container configuration. If ``options`` is a callable, it
    is run to initialize the values, otherwise it simply returns ``options`` or an empty dictionary.

    :param options: Options as a dictionary.
    :type options: callable or dict
    :return: Initial keyword arguments.
    :rtype: dict
    """
    if options:
        if callable(options):
            return options()
        return options.copy()
    return {}


def get_shared_volume_path(container_map, vol, instance=None):
    """
    Resolves a volume alias of a container configuration or a tuple of two paths to the host and container paths.

    :param container_map: Container map.
    :type container_map: dockermap.map.config.main.ContainerMap
    :param vol: SharedVolume or HostVolume tuple.
    :type vol: dockermap.map.input.HostVolume | dockermap.map.input.SharedVolume
    :param instance: Optional instance name.
    :type instance: unicode | str
    :return: Tuple of host path and container bind path.
    :rtype: tuple[unicode | str]
    """
    if isinstance(vol, HostVolume):
        c_path = resolve_value(vol.path)
        if is_path(c_path):
            return c_path, get_host_path(container_map.host.root, vol.host_path, instance)
        raise ValueError("Host-container-binding must be described by two paths or one alias name.",
                         vol)
    alias = vol.name
    c_path = resolve_value(container_map.volumes.get(alias))
    h_path = container_map.host.get_path(alias, instance)
    if c_path and h_path:
        return c_path, h_path
    raise KeyError("No host-volume information found for alias {0}.".format(alias))


def get_volumes(config, default_volume_paths, include_named):
    """
    Generates volume paths for the ``volumes`` argument during container creation.

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
        return resolve_value(default_volume_paths.get(vol.name))

    volumes = list(map(resolve_value, config.shares))
    volumes.extend(map(_bind_volume_path, config.binds))
    if include_named:
        volumes.extend(map(_attached_volume_path, config.attaches))
        volumes.extend(filter(None, map(_used_volume_path, config.uses)))
    return volumes


def get_volumes_from(map_name, container_map, config_name, config, policy, include_volumes):
    """
    Generates volume paths for the host config ``volumes_from`` argument during container creation.

    :param map_name: Container map name.
    :type map_name: unicode | str
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

    if include_volumes:
        volumes_from = [volume_str(volume_or_container_name(u.name), u.readonly)
                        for u in config.uses]
        a_parent_name = config_name if container_map.use_attached_parent_name else None
        volumes_from.extend([aname(map_name, attached.name, a_parent_name)
                             for attached in config.attaches])
    else:
        volumes_from = [volume_str(container_name(u.name), u.readonly)
                        for u in config.uses
                        if u.name not in volume_names]
    return volumes_from


def get_instance_volumes(instance_detail):
    """
    Extracts the mount points and mapped directories of a Docker container.

    :param instance_detail: Result from a container inspection.
    :type instance_detail: dict
    :return: Dictionary of volumes, with the destination (inside the container) as a key, and the source (external to
     the container) as values.
    :rtype: dict[unicode | str, unicode | str]
    """
    if 'Mounts' in instance_detail:
        return {m['Destination']: m['Source']
                for m in instance_detail['Mounts']}
    return instance_detail.get('Volumes') or {}
