# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest

from docker.utils.utils import create_host_config
from dockermap.api import ClientConfiguration, ContainerMap
from dockermap.map.input import MapConfigId, ItemType
from dockermap.map.policy.base import BasePolicy
from dockermap.map.runner import ActionConfig
from dockermap.map.runner.base import DockerClientRunner

from tests import MAP_DATA_1, CLIENT_DATA_1, CLIENT_DATA_2, MAP_DATA_1_NEW


class TestPolicyClientKwargs(unittest.TestCase):
    def setUp(self):
        self.maxDiff = 2048
        self.map_name = 'main'
        self.sample_map1 = ContainerMap('main', MAP_DATA_1_NEW)
        self.sample_map2 = ContainerMap('main', MAP_DATA_1)
        self.client_version1 = CLIENT_DATA_1['version']
        self.client_version2 = CLIENT_DATA_2['version']
        self.sample_client_config1 = client_config1 = ClientConfiguration(**CLIENT_DATA_1)
        self.sample_client_config2 = client_config2 = ClientConfiguration(**CLIENT_DATA_2)
        self.policy = BasePolicy({'main': self.sample_map1}, {'__default__': client_config1,
                                                              'legacy': client_config2})
        self.runner = DockerClientRunner(self.policy, {})

    def test_create_kwargs_without_host_config(self):
        cfg_name = 'web_server'
        cfg = self.sample_map1.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.CONTAINER, 'main', cfg_name)
        c_name = 'main.web_server'
        self.sample_client_config2.use_host_config = False
        config = ActionConfig('legacy', cfg_id, self.sample_client_config2, None, self.sample_map2, cfg)
        kwargs = self.runner.get_container_create_kwargs(config, c_name, kwargs=dict(ports=[22]))
        self.assertDictEqual(kwargs, dict(
            name=c_name,
            image='registry.example.com/nginx:latest',
            volumes=['/etc/nginx'],
            user=None,
            ports=[80, 443, 22],
            hostname='main-web-server-legacy',
            domainname=None,
        ))

    def test_host_config_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map2.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.CONTAINER, 'main', cfg_name)
        c_name = 'main.web_server'
        config = ActionConfig('legacy', cfg_id, self.sample_client_config2, None, self.sample_map2, cfg)
        kwargs = self.runner.get_container_host_config_kwargs(config, c_name,
                                                              kwargs=dict(binds=['/new_h:/new_c:rw']))
        self.assertDictEqual(kwargs, dict(
            container=c_name,
            links=[
                ('main.app_server.instance1', 'app-server-instance1'),
                ('main.app_server.instance2', 'app-server-instance2'),
            ],
            binds=[
                '/var/lib/site/config/nginx:/etc/nginx:ro',
                '/new_h:/new_c:rw',
            ],
            volumes_from=['main.app_server_socket', 'main.web_log'],
            port_bindings={80: [80], 443: [443]},
        ))

    def test_create_kwargs_with_host_config(self):
        cfg_name = 'app_server'
        cfg = self.sample_map2.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.CONTAINER, 'main', cfg_name, 'instance1')
        c_name = 'main.app_server'
        config = ActionConfig('legacy', cfg_id, self.sample_client_config2, None, self.sample_map2, cfg)
        hc_kwargs = dict(binds=['/new_h:/new_c:rw'])
        kwargs = self.runner.get_container_create_kwargs(config, c_name, kwargs=dict(host_config=hc_kwargs))
        self.assertDictEqual(kwargs, dict(
            name=c_name,
            image='registry.example.com/app:custom',
            volumes=[
                '/var/lib/app/config',
                '/var/lib/app/data'
            ],
            user='2000',
            hostname='main-app-server-legacy',
            domainname=None,
            ports=[8880],
            host_config=create_host_config(
                links={},
                binds=[
                    '/var/lib/site/config/app1:/var/lib/app/config:ro',
                    '/var/lib/site/data/app1:/var/lib/app/data:rw',
                    '/new_h:/new_c:rw',
                ],
                volumes_from=['main.app_log', 'main.app_server_socket'],
                port_bindings={},
                version=self.client_version2,
            ),
        ))

    def test_create_kwargs_with_host_config_and_volumes_networks(self):
        cfg_name = 'app_server'
        cfg = self.sample_map1.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.CONTAINER, 'main', cfg_name, 'instance1')
        c_name = 'main.app_server'
        config = ActionConfig('__default__', cfg_id, self.sample_client_config1, None, self.sample_map1, cfg)
        hc_kwargs = dict(binds=['/new_h:/new_c:rw'])
        kwargs = self.runner.get_container_create_kwargs(config, c_name, kwargs=dict(host_config=hc_kwargs))
        self.assertDictEqual(kwargs, dict(
            name=c_name,
            image='registry.example.com/app:custom',
            volumes=[
                '/var/lib/app/config',
                '/var/lib/app/data',
                '/var/lib/app/log',
                '/var/lib/app/socket',
            ],
            user='2000',
            hostname='main-app-server',
            domainname=None,
            ports=[8880],
            networking_config={'EndpointsConfig': {'main.app': {}}},
            host_config=create_host_config(
                links={},
                binds=[
                    '/var/lib/site/config/app1:/var/lib/app/config:ro',
                    '/var/lib/site/data/app1:/var/lib/app/data:rw',
                    'main.app_log:/var/lib/app/log:rw',
                    'main.app_server_socket:/var/lib/app/socket:rw',
                    '/new_h:/new_c:rw',
                ],
                volumes_from=[],
                port_bindings={},
                version=self.client_version1,
            ),
        ))

    def test_attached_create_kwargs_without_host_config(self):
        cfg_name = 'app_server'
        cfg = self.sample_map2.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.VOLUME, 'main', cfg_name, 'app_server_socket')
        c_name = 'main.app_server'
        config = ActionConfig('legacy', cfg_id, self.sample_client_config2, None, self.sample_map2, cfg)
        kwargs = self.runner.get_attached_container_create_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            name=c_name,
            image=BasePolicy.base_image,
            volumes=['/var/lib/app/socket'],
            user='2000',
            network_disabled=True,
        ))

    def test_attached_host_config_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map2.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.VOLUME, 'main', cfg_name, 'app_server_socket')
        c_name = 'main.app_server'
        config = ActionConfig('legacy', cfg_id, self.sample_client_config2, None, self.sample_map2, cfg)
        kwargs = self.runner.get_attached_container_host_config_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(container=c_name))

    def test_attached_preparation_create_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map2.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.VOLUME, 'main', cfg_name, 'app_server_socket')
        v_name = 'main.app_server_socket'
        config = ActionConfig('legacy', cfg_id, self.sample_client_config2, None, self.sample_map2, cfg)
        kwargs = self.runner.get_attached_preparation_create_kwargs(config, v_name, 'app_server_socket')
        self.assertDictEqual(kwargs, dict(
            image=BasePolicy.core_image,
            command='chown -R 2000:2000 /var/lib/app/socket && chmod -R u=rwX,g=rX,o= /var/lib/app/socket',
            user='root',
            host_config=create_host_config(
                volumes_from=[v_name],
                version=self.client_version2,
            ),
            network_disabled=True,
        ))

    def test_attached_preparation_create_kwargs_with_volumes(self):
        cfg_name = 'app_server'
        cfg = self.sample_map1.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.VOLUME, 'main', cfg_name, 'app_server_socket')
        v_name = 'main.app_server_socket'
        config = ActionConfig('__default__', cfg_id, self.sample_client_config1, None, self.sample_map1, cfg)
        kwargs = self.runner.get_attached_preparation_create_kwargs(config, v_name, 'app_server_socket')
        self.assertDictEqual(kwargs, dict(
            image=BasePolicy.core_image,
            command='chown -R 2000:2000 /volume-tmp && chmod -R u=rwX,g=rX,o= /volume-tmp',
            user='root',
            volumes=['/volume-tmp'],
            host_config=create_host_config(
                binds=['main.app_server_socket:/volume-tmp'],
                version=self.client_version1,
            ),
            network_disabled=True,
        ))

    def test_attached_preparation_host_config_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map2.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.VOLUME, 'main', cfg_name, 'app_server_socket')
        c_name = 'temp'
        v_name = 'main.app_server_socket'
        config = ActionConfig('legacy', cfg_id, self.sample_client_config2, None, self.sample_map2, cfg)
        kwargs = self.runner.get_attached_preparation_host_config_kwargs(config, c_name, v_name)
        self.assertDictEqual(kwargs, dict(
            container=c_name,
            volumes_from=[v_name],
        ))

    def test_network_setting(self):
        cfg_name = 'app_extra'
        cfg = self.sample_map2.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.CONTAINER, 'main', cfg_name)
        c_name = 'main.app_extra'
        config = ActionConfig('__default__', cfg_id, self.sample_client_config2, None, self.sample_map2, cfg)
        kwargs = self.runner.get_container_host_config_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            binds=[],
            container=c_name,
            links=[],
            network_mode='container:main.app_server.instance1',
            port_bindings={},
            volumes_from=[],
        ))

    def test_restart_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map1.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.CONTAINER, 'main', cfg_name)
        c_name = 'main.web_server'
        config = ActionConfig('__default__', cfg_id, self.sample_client_config1, None, self.sample_map1, cfg)
        kwargs = self.runner.get_container_restart_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            container=c_name,
            timeout=5,
        ))

    def test_stop_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map1.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.CONTAINER, 'main', cfg_name)
        c_name = 'main.web_server'
        config = ActionConfig('__default__', cfg_id, self.sample_client_config1, None, self.sample_map1, cfg)
        kwargs = self.runner.get_container_stop_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            container=c_name,
            timeout=5,
        ))

    def test_remove_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map1.get_existing(cfg_name)
        cfg_id = MapConfigId(ItemType.CONTAINER, 'main', cfg_name)
        c_name = 'main.web_server'
        config = ActionConfig('__default__', cfg_id, self.sample_client_config1, None, self.sample_map1, cfg)
        kwargs = self.runner.get_container_remove_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            container=c_name,
        ))
