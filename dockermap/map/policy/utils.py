# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
import six

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
    :type user_value: int or tuple or unicode
    :return: User name or id.
    :rtype: unicode
    """
    user = resolve_value(user_value)
    if not user and user != 0 and user != '0':
        return None
    if isinstance(user, tuple):
        return user[0]
    if isinstance(user, int):
        return six.text_type(user)
    return user.partition(':')[0]


def update_kwargs(kwargs, *updates):
    """
    Utility function for merging multiple keyword arguments, depending on their type:

    * Non-existent keys are added.
    * Existing lists are extended (the kwargs entry should be a list, whereas the following updates can also be tuples).
    * Nested dictionaries are updated, overriding previous key-value assignments.
    * Other items are simply overwritten (just like in a regular dictionary update).

    Lists/tuples and dictionaries are (shallow-)copied before adding. This function does not recurse.

    :param kwargs: Base keyword arguments.
    :type kwargs: dict
    :param updates: Dictionaries to update ``kwargs`` with.
    :type updates: tuple[dict]
    :return: A merged dictionary of keyword arguments.
    :rtype: dict
    """
    for update in updates:
        if not update:
            continue
        for key, val in six.iteritems(update):
            u_item = resolve_value(val)
            if not u_item:
                continue
            kw_item = kwargs.get(key)
            if isinstance(u_item, (tuple, list)):
                if kw_item:
                    kw_item.extend(u_item)
                else:
                    kwargs[key] = u_item[:]
            elif isinstance(u_item, dict):
                if kw_item:
                    kw_item.update(u_item)
                else:
                    kwargs[key] = u_item.copy()
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


def get_volumes(container_map, config):
    """
    Generates volume paths for the ``volumes`` argument during container creation.

    :param container_map: Container map.
    :type container_map: dockermap.map.container.ContainerMap
    :param config: Container configuration.
    :type config: dockermap.map.config.ContainerConfiguration
    :return: List of shared volume mount points.
    :rtype: list[unicode]
    """
    volumes = [resolve_value(s) for s in config.shares]
    volumes.extend([resolve_value(container_map.volumes[b.volume]) for b in config.binds])
    return volumes


def get_inherited_volumes(config):
    """
    Generates external volume names for the ``volumes_from`` argument for the container start. If applicable includes a
    read-only access indicator, but not the container map name.

    :param config: Container configuration.
    :type config: dockermap.map.config.ContainerConfiguration
    :return: List of used volume names.
    :rtype: itertools.chain[unicode]
    """
    def volume_str(u):
        vol = u.volume
        if u.readonly:
            return '{0}:ro'.format(vol)
        return vol

    return itertools.chain(map(volume_str, config.uses), config.attaches)


def get_host_binds(container_map, config, instance):
    """
    Generates the dictionary entries of host volumes of a container configuration.

    :param container_map: Container map.
    :type container_map: dockermap.map.container.ContainerMap
    :param config: Container configuration.
    :type config: dockermap.map.config.ContainerConfiguration
    :param instance: Instance name. Pass ``None`` if not applicable.
    :type instance: unicode
    :return: Dictionary of shared volumes with host volumes and the read-only flag.
    :rtype: dict[unicode, dict]
    """
    binds = {}
    for alias, readonly in config.binds:
        share = container_map.host.get(alias, instance)
        if share:
            vol = resolve_value(container_map.volumes[alias])
            bind = dict(bind=vol, ro=readonly)
            binds[share] = bind
        else:
            raise KeyError("No host volume definition found for alias '{0}'.".format(alias))
    return binds


def get_port_bindings(container_config, client_config):
    """
    Generates the input dictionary contents for the ``port_bindings`` argument.

    :param container_config: Container configuration.
    :type container_config: dockermap.map.config.ContainerConfiguration
    :param client_config: Client configuration.
    :type client_config: dockermap.map.config.ClientConfiguration
    :return: Dictionary of ports with mapped port, and if applicable, with bind address
    :rtype: dict[unicode, unicode | int | tuple]
    """
    port_bindings = {}
    for port_binding in container_config.exposes:
        exposed_port = port_binding.exposed_port
        bind_port = resolve_value(port_binding.host_port)
        interface = resolve_value(port_binding.interface)
        if interface:
            bind_addr = resolve_value(client_config.interfaces.get(interface))
            if not bind_addr:
                raise ValueError("Address for interface '{0}' not found in client configuration.".format(interface))
            port_bindings[exposed_port] = (bind_addr, bind_port)
        elif bind_port:
            port_bindings[exposed_port] = bind_port
    return port_bindings


def is_initial(container_state):
    """
    Checks if a container with the given status information has ever been started.

    :param container_state: Container status dictionary.
    :type container_state: dict
    :return: ``True`` if the container has never been started before, ``False`` otherwise.
    :rtype: bool
    """
    return container_state['StartedAt'] == INITIAL_START_TIME
