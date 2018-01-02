# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

import docker


if docker.version_info[0] == 1:
    from docker.utils import utils as docker_utils

    APIClient = docker.Client
    HostConfig = docker_utils.create_host_config
    NetworkingConfig = docker_utils.create_networking_config
    EndpointConfig = docker_utils.create_endpoint_config
    IPAMPool = docker_utils.create_ipam_pool
    IPAMConfig = docker_utils.create_ipam_config
else:
    from docker import types as docker_types

    APIClient = docker.APIClient
    HostConfig = docker_types.HostConfig
    NetworkingConfig = docker_types.NetworkingConfig
    EndpointConfig = docker_types.EndpointConfig
    IPAMPool = docker_types.IPAMPool
    IPAMConfig = docker_types.IPAMConfig
