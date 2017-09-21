# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from ...functional import resolve_value
from ..config.host_volume import get_host_path
from ..input import is_path, HostVolume

INITIAL_START_TIME = '0001-01-01T00:00:00Z'


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
    volume_config = resolve_value(container_map.volumes.get(alias))
    h_path = container_map.host.get_path(alias, instance)
    if volume_config and h_path:
        return volume_config.default_path, h_path
    raise KeyError("No host-volume information found for alias {0}.".format(alias))


def get_instance_volumes(instance_detail, check_names):
    """
    Extracts the mount points and mapped directories or names of a Docker container.

    :param instance_detail: Result from a container inspection.
    :type instance_detail: dict
    :param check_names: Whether to check for named volumes.
    :type check_names: bool
    :return: Dictionary of volumes, with the destination (inside the container) as a key, and the source (external to
     the container) as values. If ``check_names`` is ``True``, the value contains the mounted volume name instead.
    :rtype: dict[unicode | str, unicode | str]
    """
    if 'Mounts' in instance_detail:
        if check_names:
            return {m['Destination']: m.get('Name') or m['Source']
                    for m in instance_detail['Mounts']}
        return {m['Destination']: m['Source']
                for m in instance_detail['Mounts']}
    return instance_detail.get('Volumes') or {}
