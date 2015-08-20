# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest

from docker.utils.utils import create_host_config
from dockermap.api import ClientConfiguration, ContainerMap
from dockermap.map.policy.base import BasePolicy

from tests import MAP_DATA_1, CLIENT_DATA_1


class TestPolicyClientKwargs(unittest.TestCase):
    def setUp(self):
        self.maxDiff = 2048
        self.map_name = 'main'
        self.sample_map = ContainerMap('main', MAP_DATA_1)
        self.sample_client_config = ClientConfiguration(**CLIENT_DATA_1)

    def test_create_kwargs_without_host_config(self):
        cfg_name = 'web_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        kwargs = BasePolicy.get_create_kwargs(self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config,
                                              c_name, None, include_host_config=False, kwargs=dict(ports=[22]))
        self.assertEqual(kwargs, dict(
            name=c_name,
            image='registry.example.com/nginx',
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
        kwargs = BasePolicy.get_host_config_kwargs(self.sample_map, cfg_name, cfg, '__default__',
                                                   self.sample_client_config, c_name, None,
                                                   kwargs=dict(binds={'/new_h': {'bind': '/new_c', 'ro': False}}))
        self.assertEqual(kwargs, dict(
            container=c_name,
            links={},
            binds={
                '/var/lib/site/config/nginx': {'bind': '/etc/nginx', 'ro': True},
                '/new_h': {'bind': '/new_c', 'ro': False},
            },
            volumes_from=['main.app_server_socket', 'main.web_log'],
            port_bindings={80: 80, 443: 443},
        ))

    def test_create_kwargs_with_host_config(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.app_server'
        hc_kwargs = dict(binds={'/new_h': {'bind': '/new_c', 'ro': False}})
        kwargs = BasePolicy.get_create_kwargs(self.sample_map, cfg_name, cfg, '__default__',
                                              self.sample_client_config, c_name, 'instance1',
                                              include_host_config=True, kwargs=dict(host_config=hc_kwargs))
        self.assertEqual(kwargs, dict(
            name=c_name,
            image='registry.example.com/app',
            volumes=[
                '/var/lib/app/config',
                '/var/lib/app/data'
            ],
            user='2000',
            hostname='main.app_server',
            domainname=None,
            ports=[],
            host_config=create_host_config(
                links={},
                binds={
                    '/var/lib/site/config/app1': {'bind': '/var/lib/app/config', 'ro': True},
                    '/var/lib/site/data/app1': {'bind': '/var/lib/app/data', 'ro': False},
                    '/new_h': {'bind': '/new_c', 'ro': False},
                },
                volumes_from=['main.app_log', 'main.app_server_socket'],
                port_bindings={},
            ),
        ))

    def test_attached_create_kwargs_without_host_config(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.app_server'
        alias = 'app_server_socket'
        kwargs = BasePolicy.get_attached_create_kwargs(self.sample_map, cfg_name, cfg, '__default__',
                                                       self.sample_client_config, c_name, alias,
                                                       include_host_config=True)
        self.assertEqual(kwargs, dict(
            name=c_name,
            image=BasePolicy.base_image,
            volumes=['/var/lib/app/socket'],
            user='2000',
        ))

    def test_attached_host_config_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.app_server'
        alias = 'app_server_socket'
        kwargs = BasePolicy.get_attached_host_config_kwargs(self.sample_map, cfg_name,  cfg, '__default__',
                                                            self.sample_client_config, c_name, alias)
        self.assertEqual(kwargs, dict(container=c_name))

    def test_attached_preparation_create_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'temp'
        alias = 'app_server_socket'
        v_name = 'main.app_server_socket'
        kwargs = BasePolicy.get_attached_preparation_create_kwargs(self.sample_map, cfg_name, cfg, '__default__',
                                                                   self.sample_client_config, c_name, alias,
                                                                   v_name, include_host_config=True)
        self.assertEqual(kwargs, dict(
            image=BasePolicy.core_image,
            command='chown -R 2000:2000 /var/lib/app/socket && chmod -R u=rwX,g=rX,o= /var/lib/app/socket',
            user='root',
            host_config=create_host_config(
                volumes_from=[v_name],
            )
        ))

    def test_attached_preparation_host_config_kwargs(self):
        cfg_name = 'app_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'temp'
        alias = 'app_server_socket'
        v_name = 'main.app_server_socket'
        kwargs = BasePolicy.get_attached_preparation_host_config_kwargs(self.sample_map, cfg_name, cfg, '__default__',
                                                                        self.sample_client_config, c_name, alias,
                                                                        v_name)
        self.assertEqual(kwargs, dict(
            container='temp',
            volumes_from=[v_name],
        ))

    def test_restart_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        kwargs = BasePolicy.get_restart_kwargs(self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config,
                                               c_name, None)
        self.assertEqual(kwargs, dict(
            container=c_name,
        ))

    def test_stop_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        kwargs = BasePolicy.get_stop_kwargs(self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config,
                                            c_name, None)
        self.assertEqual(kwargs, dict(
            container=c_name,
            timeout=10,
        ))

    def test_remove_kwargs(self):
        cfg_name = 'web_server'
        cfg = self.sample_map.get_existing(cfg_name)
        c_name = 'main.web_server'
        kwargs = BasePolicy.get_remove_kwargs(self.sample_map, cfg_name, cfg, '__default__', self.sample_client_config,
                                              c_name, None)
        self.assertEqual(kwargs, dict(
            container=c_name,
        ))
