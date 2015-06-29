# -*- coding: utf-8 -*-
from __future__ import unicode_literals

MAP_DATA_1 = {
    'repository': 'registry.example.com',
    'host_root': '/var/lib/site',
    'web_server': { # Configure container creation and startup
        'image': 'nginx',
        # If volumes are not shared with any other container, assigning
        # an alias in "volumes" is possible, but not neccessary:
        'binds': {'/etc/nginx': ('config/nginx', 'ro')},
        'uses': 'app_server_socket',
        'attaches': 'web_log',
        'exposes': {
            80: 80,
            443: 443,
        }
    },
    'app_server': {
        'image': 'app',
        'instances': ('instance1', 'instance2'),
        'binds': (
            {'app_config': 'ro'},
            'app_data',
        ),
        'attaches': ('app_log', 'app_server_socket'),
        'user': 2000,
        'permissions': 'u=rwX,g=rX,o=',
    },
    'volumes': { # Configure volume paths inside containers
        'web_log': '/var/log/nginx',
        'app_server_socket': '/var/lib/app/socket',
        'app_config': '/var/lib/app/config',
        'app_log': '/var/lib/app/log',
        'app_data': '/var/lib/app/data',
    },
    'host': { # Configure volume paths on the Docker host
        'app_config': {
            'instance1': 'config/app1',
            'instance2': 'config/app2',
        },
        'app_data': {
            'instance1': 'data/app1',
            'instance2': 'data/app2',
        },
    },
}

CLIENT_DATA_1 = {
    'interfaces': {'private': '10.0.0.11'},
}
