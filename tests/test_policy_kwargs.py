# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest

from docker.utils.utils import create_host_config
from dockermap.api import ClientConfiguration, ContainerMap
from dockermap.map.policy.base import BasePolicy
from dockermap.map.runner import ActionConfig
from dockermap.map.runner.base import DockerClientRunner

from tests import MAP_DATA_1, CLIENT_DATA_1


class TestPolicyClientKwargs(unittest.TestCase):
    def setUp(self):
        self.maxDiff = 2048
        self.map_name = 'main'
        self.sample_map = ContainerMap('main', MAP_DATA_1)
        self.client_version = CLIENT_DATA_1['version']
        self.sample_client_config = ClientConfiguration(**CLIENT_DATA_1)
        self.policy = BasePolicy({'main': self.sample_map}, {'__default__': self.sample_client_config})
        self.runner = DockerClientRunner(self.policy, {})

    def test_create_kwargs_without_host_config(self):
        cfg_name = 'web_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        self.sample_client_config.use_host_config = False
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              None)
        kwargs = self.runner.get_create_kwargs(config, c_name, kwargs=dict(ports=[22]))
        self.assertDictEqual(kwargs, dict(
            name=c_name,
            image='registry.example.com/nginx:latest',
            volumes=['/etc/nginx'],
            user=None,
            ports=[80, 443, 22],
            hostname='main.web_server',
            domainname=None,
        ))

    def test_host_config_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              None)
        kwargs = self.runner.get_host_config_kwargs(config, c_name,
                                                    kwargs=dict(binds=['/new_h:/new_c:rw']))
        self.assertDictEqual(kwargs, dict(
            container=c_name,
            links=[
                ('main.app_server.instance1', 'app_server.instance1'),
                ('main.app_server.instance2', 'app_server.instance2'),
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
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.app_server'
        self.sample_client_config.use_host_config = True
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              'instance1')
        hc_kwargs = dict(binds=['/new_h:/new_c:rw'])
        kwargs = self.runner.get_create_kwargs(config, c_name, kwargs=dict(host_config=hc_kwargs))
        self.assertDictEqual(kwargs, dict(
            name=c_name,
            image='registry.example.com/app:custom',
            volumes=[
                '/var/lib/app/config',
                '/var/lib/app/data'
            ],
            user='2000',
            hostname='main.app_server',
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
                version=self.client_version,
            ),
        ))

    def test_attached_create_kwargs_without_host_config(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.app_server'
        alias = 'app_server_socket'
        self.sample_client_config.use_host_config = False
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              alias)
        kwargs = self.runner.get_attached_create_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            name=c_name,
            image=BasePolicy.base_image,
            volumes=['/var/lib/app/socket'],
            user='2000',
            network_disabled=True,
        ))

    def test_attached_host_config_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.app_server'
        alias = 'app_server_socket'
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              alias)
        kwargs = self.runner.get_attached_host_config_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(container=c_name))

    def test_attached_preparation_create_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        alias = 'app_server_socket'
        v_name = 'main.app_server_socket'
        self.sample_client_config.use_host_config = True
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              alias)
        kwargs = self.runner.get_attached_preparation_create_kwargs(config, v_name)
        self.assertDictEqual(kwargs, dict(
            image=BasePolicy.core_image,
            command='chown -R 2000:2000 /var/lib/app/socket && chmod -R u=rwX,g=rX,o= /var/lib/app/socket',
            user='root',
            host_config=create_host_config(
                volumes_from=[v_name],
                version=self.client_version,
            ),
            network_disabled=True,
        ))

    def test_attached_preparation_host_config_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'temp'
        alias = 'app_server_socket'
        v_name = 'main.app_server_socket'
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              alias)
        kwargs = self.runner.get_attached_preparation_host_config_kwargs(config, c_name, v_name)
        self.assertDictEqual(kwargs, dict(
            container=c_name,
            volumes_from=[v_name],
        ))

    def test_network_setting(self):
        cfg_name = 'app_extra'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.app_extra'
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              None)
        kwargs = self.runner.get_host_config_kwargs(config, c_name)
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
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              None)
        kwargs = self.runner.get_restart_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            container=c_name,
            timeout=5,
        ))

    def test_stop_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              None)
        kwargs = self.runner.get_stop_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            container=c_name,
            timeout=5,
        ))

    def test_remove_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        config = ActionConfig('main', self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config, None,
                              None)
        kwargs = self.runner.get_remove_kwargs(config, c_name)
        self.assertDictEqual(kwargs, dict(
            container=c_name,
        ))
