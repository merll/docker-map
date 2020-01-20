# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from distutils.version import StrictVersion
try:
    from docker.constants import MINIMUM_DOCKER_API_VERSION
except ImportError:
    MINIMUM_DOCKER_API_VERSION = '1.00'


SKIP_LEGACY_TESTS = StrictVersion('1.19') < StrictVersion(MINIMUM_DOCKER_API_VERSION)

MAP_DATA_1 = {
    'repository': 'registry.example.com',
    'default_tag': 'custom',
    'host_root': '/var/lib/site',
    'web_server': { # Configure container creation and startup
        'image': 'nginx:latest',
        # If volumes are not shared with any other container, assigning
        # an alias in "volumes" is possible, but not neccessary:
        'binds': {'/etc/nginx': ('config/nginx', 'ro')},
        'uses': 'app_server_socket',
        'attaches': 'web_log',
        'links': ['app_server.instance1', 'app_server.instance2'],
        'exposes': {
            80: 80,
            443: 443,
        },
        'stop_timeout': 5,
    },
    'app_server': {
        'image': 'app',
        'instances': ('instance1', 'instance2'),
        'exposes': [8880],
        'binds': (
            {'app_config': 'ro'},
            'app_data',
        ),
        'attaches': ('app_log', 'app_server_socket'),
        'user': 2000,
        'permissions': 'u=rwX,g=rX,o=',
    },
    'app_extra': {
        'network_mode': 'app_server.instance1',
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
MAP_DATA_1_NEW = {
    'repository': 'registry.example.com',
    'default_tag': 'custom',
    'host_root': '/var/lib/site',
    'web_server': {
        'image': 'nginx:latest',
        # If volumes are not shared with any other container, assigning
        # an alias in "volumes" is possible, but not neccessary:
        'binds': {'/etc/nginx': ('config/nginx', 'ro')},
        'uses': [('app_server_socket', '/var/lib/app/custom/socket')],
        'attaches': [('web_log', '/var/log/nginx')],
        'networks': {
            'bridge': None,
            'app': {
                'links': [('app_server.instance1', 'i1'),
                          ('app_server.instance2', 'i2')],
            }
        },
        'exposes': {
            80: 80,
            443: 443,
        },
        'stop_timeout': 5,
    },
    'app_server': {
        'image': 'app',
        'instances': ('instance1', 'instance2'),
        'exposes': [8880],
        'binds': (
            {'app_config': 'ro'},
            'app_data',
        ),
        'networks': 'app',
        'attaches': ('app_log', ('app_server_socket', '/var/lib/app/socket')),
        'user': 2000,
        'permissions': 'u=rwX,g=rX,o=',
        'stop_signal': 'SIGTERM',
        'stop_timeout': 10,
        'healthcheck': {
            'test': ['curl', 'http://localhost/'],
            'interval': '1m',
            'timeout': '1000ms',
            'retries': 3,
            'start_period': '5s',
        },
    },
    'app_extra': {
        'networks': 'app',
    },
    'networks': {
        'app': None,
    },
    'volumes': { # Configure volume paths inside containers
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

MAP_DATA_2 = {
    'repository': 'registry.example.com',
    'host_root': '/var/lib/site',
    'containers': {
        'svc': {
        },
        'svc2': {
        },
        'sub_svc': {
            'links': 'sub_sub_svc',
        },
        'sub_sub_svc': {
        },
        'net_sub_svc': {
        },
        'net_svc': {
            'networks': [('app_net1', {
                'links': 'net_sub_svc',
            })],
        },
        'abstract_config': {
            'abstract': True,
            'image': 'server',
            'binds': {
                'app_config': 'ro',
            },
            'links': [('svc', 'svc_alias1')],
            'uses': 'redis.redis_socket',
            'attaches': 'app_log',
            'user': 'app_user',
            'permissions': 'u=rwX,g=rX,o=',
        },
        'server': {
            'extends': 'abstract_config',
            'binds': {
                'app_data': 'rw',
            },
            'links': [('svc', 'svc_alias2')],
            'attaches': 'server_log',
            'user': 'server_user',
            'exposes': {
                8443: (8443, 'private'),
            },
            'create_options': {
                'mem_limit': '1g',
                'cpu_shares': 15,
            },
            'host_config': {
                'restart_policy': {
                    'MaximumRetryCount': 3,
                    'Name': 'always',
                },
            },
        },
        'server2': {
            'extends': 'server',
            'links': ['svc2']
        },
        'server3': {
            'networks': ['app_net1', ('app_net2', 'server_x')],
        },
        'abstract_worker': {
            'abstract': True,
            'extends': 'abstract_config',
            'binds': {
                'app_data': 'rw',
            },
            'create_options': {
                'entrypoint': 'celery',
            },
            'host_config': {
                'restart_policy': {
                    'MaximumRetryCount': 0,
                    'Name': 'always',
                },
            },
        },
        'worker': {
            'extends': 'abstract_worker',
            'create_options': {
                'mem_limit': '2g',
                'cpu_shares': 10,
                'command': 'worker -A MyApp -Q queue1,queue2',
            },
        },
        'worker_q2': {
            'extends': 'abstract_worker',
            'create_options': {
                'mem_limit': '1g',
                'cpu_shares': 30,
                'command': 'worker -A MyApp -Q queue2',
            },
        },
        'redis': {
            'image': 'redis',
            'instances': ['queue', 'cache'],
            'binds': {
                '/etc/redis': ('redis/config', 'ro'),
                '/var/lib/redis': 'redis/data',
            },
            'links': 'sub_svc',
            'attaches': ['redis_socket', ('redis_log', '/var/log/redis')],
            'user': 'redis',
            'permissions': 'u=rwX,g=rX,o=',
            'host_config': {
                'restart_policy': {
                    'MaximumRetryCount': 0,
                    'Name': 'always',
                },
            },
        },
        'persistent_one': {
            'persistent': True,
        },
    },
    'volumes': {
        'redis_socket': '/var/run/redis',
        'server_log': '/var/lib/server/log',
        'app_data': '/var/lib/app/data',
        'app_config': '/var/lib/app/config',
        'app_log': '/var/lib/app/log',
    },
    'host': {
        'app_data': 'app/data',
        'app_config': 'app/config',
    },
    'networks': {
        'app_net1': {'driver': 'bridge'},
        'app_net2': None,
    },
    'groups': {
        'group1': ['server', 'worker', 'worker_q2'],
    }
}

MAP_DATA_3 = {
    'repository': 'registry.example.com',
    'host_root': '/var/lib/site',
    'containers': {
        'abstract_config': {
            'abstract': True,
            'image': 'server',
            'binds': {
                '/var/lib/web/config': ['web/config', 'ro'],
            },
            'attaches': 'web_log',
            'permissions': 'u=rwX,g=rX,o=',
        },
        'server': {
            'extends': 'abstract_config',
        },
    },
    'volumes': {
        'web_log': '/var/lib/web/log',
    }
}

CLIENT_DATA_1 = {
    'interfaces': {'private': '10.0.0.11'},
    'version': '1.25',
}
CLIENT_DATA_2 = {
    'interfaces': {'private': '10.0.0.11'},
    'version': '1.19',
}
