# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from ..config import get_host_path
from ..input import is_path
from ...functional import resolve_value

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
    * Existing lists or tuples are extended.
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
                    kw_item.extend(u_list)
                elif isinstance(kw_item, tuple):
                    new_list = list(kw_item)
                    new_list.extend(u_list)
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


def get_shared_volume_path(container_map, volume, instance=None):
    """
    Resolves a volume alias of a container configuration or a tuple of two paths to the host and container paths.

    :param container_map: Container map.
    :type container_map: dockermap.map.container.ContainerMap
    :param volume: Volume alias or tuple of paths.
    :type volume: unicode | str | AbstractLazyObject | tuple[unicode | str] | tuple[AbstractLazyObject]
    :param instance: Optional instance name.
    :type instance: unicode | str
    :return: Tuple of host path and container bind path.
    :rtype: tuple[unicode | str]
    """
    if isinstance(volume, tuple):
        v_len = len(volume)
        if v_len == 2:
            c_path = resolve_value(volume[0])
            if is_path(c_path):
                return c_path, get_host_path(container_map.host.root, volume[1], instance)
        raise ValueError("Host-container-binding must be described by two paths or one alias name. "
                         "Found {0}.".format(volume))
    c_path = resolve_value(container_map.volumes.get(volume))
    h_path = container_map.host.get_path(volume, instance)
    if c_path:
        return c_path, h_path
    raise KeyError("No host-volume information found for alias {0}.".format(volume))


def get_volumes(container_map, config):
    """
    Generates volume paths for the ``volumes`` argument during container creation.

    :param container_map: Container map.
    :type container_map: dockermap.map.container.ContainerMap
    :param config: Container configuration.
    :type config: dockermap.map.config.ContainerConfiguration
    :return: List of shared volume mount points.
    :rtype: list[unicode | str]
    """
    def _volume_path(vol):
        if isinstance(vol, tuple) and len(vol) == 2:
            return resolve_value(vol[0])
        v_path = resolve_value(container_map.volumes.get(vol))
        if v_path:
            return v_path
        raise KeyError("No host-volume information found for alias {0}.".format(vol))

    volumes = [resolve_value(s) for s in config.shares]
    volumes.extend([_volume_path(b.volume) for b in config.binds])
    return volumes


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

