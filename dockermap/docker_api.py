# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

import docker


CLIENT_FEATURES = [
    ('host_config', '1.15'),
    ('networks', '1.21'),
    ('volumes', '1.21'),
    ('container_update', '1.22'),
]


if docker.version_info[0] == 1:
    from docker.utils import utils as docker_utils

    APIClient = docker.Client
    HostConfig = docker_utils.create_host_config
    NetworkingConfig = docker_utils.create_networking_config
    EndpointConfig = docker_utils.create_endpoint_config
    IPAMPool = docker_utils.create_ipam_pool
    IPAMConfig = docker_utils.create_ipam_config

    CLIENT_FEATURES.extend([
        ('stop_timeout', '100.0'),
        ('healthcheck', '100.0'),
    ])
else:
    from docker import types as docker_types

    APIClient = docker.APIClient
    HostConfig = docker_types.HostConfig
    NetworkingConfig = docker_types.NetworkingConfig
    EndpointConfig = docker_types.EndpointConfig
    IPAMPool = docker_types.IPAMPool
    IPAMConfig = docker_types.IPAMConfig

    CLIENT_FEATURES.extend([
        ('stop_timeout', '1.25'),
        ('healthcheck', '1.24'),
    ])
