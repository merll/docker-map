# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools

from ...functional import resolve_value
from ...shortcuts import chown, chmod
from ..policy.utils import get_shared_volume_path


def get_host_binds(container_map, config, instance):
    """
    Generates the dictionary entries of host volumes of a container configuration.

    :param container_map: Container map.
    :type container_map: dockermap.map.container.ContainerMap
    :param config: Container configuration.
    :type config: dockermap.map.config.ContainerConfiguration
    :param instance: Instance name. Pass ``None`` if not applicable.
    :type instance: unicode | str
    :return: List of shared volumes with host volumes and the read-only flag.
    :rtype: list[unicode | str]
    """
    return ['{0[1]}:{0[0]}:{1}'.format(get_shared_volume_path(container_map, shared_volume.volume, instance),
                                       'ro' if shared_volume.readonly else 'rw')
            for shared_volume in config.binds]


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
    :type container_config: dockermap.map.config.ContainerConfiguration
    :param client_config: Client configuration.
    :type client_config: dockermap.map.config.ClientConfiguration
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


def get_preparation_cmd(container_config, path):
    """
    Generates the command lines for adjusting a volume's ownership and permission flags. Returns an empty list if there
    is nothing to adjust.

    :param container_config: Container configuration.
    :type container_config: dockermap.map.config.ContainerConfiguration
    :param path: Path to adjust permissions on.
    :type path: unicode | str
    :return: Resulting command strings.
    :rtype: list[unicode | str]
    """
    def _get_cmd():
        if user:
            yield chown(user, path)
        if permissions:
            yield chmod(permissions, path)

    user = resolve_value(container_config.user)
    permissions = container_config.permissions
    return list(_get_cmd())
