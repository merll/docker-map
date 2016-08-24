# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest

from dockermap.map.container import ContainerMap
from dockermap.map.input import SharedVolume, PortBinding, NotSet, ContainerLink
from tests import MAP_DATA_2, MAP_DATA_3


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.sample_map = ContainerMap('main', MAP_DATA_2, use_attached_parent_name=True)
        self.ext_main = self.sample_map.get_extended_map()
        self.simple_map = ContainerMap('simple', MAP_DATA_3)
        self.ext_simple = self.simple_map.get_extended_map()

    def test_single_config(self):
        cfg = self.sample_map.get_existing('abstract_config')
        self.assertTrue(cfg.abstract)
        self.assertEqual(cfg.image, 'server')
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, ['app_log'])
        self.assertEqual(cfg.user, 'app_user')
        self.assertEqual(cfg.permissions, 'u=rwX,g=rX,o=')

    def test_merge_with_dict(self):
        cfg = self.sample_map.get_existing('abstract_config')
        merge_dict = MAP_DATA_2['containers']['server']
        cfg.merge(merge_dict)
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, ['app_log', 'server_log'])
        self.assertEqual(cfg.user, 'server_user')
        self.assertEqual(cfg.exposes, [PortBinding(8443, 8443, 'private', False)])
        self.assertEqual(cfg.links, [ContainerLink('svc', 'svc_alias1'), ContainerLink('svc', 'svc_alias2')])
        self.assertEqual(cfg.create_options, {
            'mem_limit': '1g',
            'cpu_shares': 15,
        })
        self.assertEqual(cfg.host_config, {
            'restart_policy': {
                'MaximumRetryCount': 3,
                'Name': 'always',
            },
        })

    def test_merge_with_dict_lists_only(self):
        cfg = self.sample_map.get_existing('abstract_config')
        merge_dict = MAP_DATA_2['containers']['server']
        cfg.merge(merge_dict, lists_only=True)
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, ['app_log', 'server_log'])
        self.assertEqual(cfg.user, 'app_user')
        self.assertEqual(cfg.exposes, [PortBinding(8443, 8443, 'private', False)])
        self.assertEqual(cfg.links, [ContainerLink('svc', 'svc_alias1'), ContainerLink('svc', 'svc_alias2')])
        self.assertIs(cfg.create_options, NotSet)
        self.assertIs(cfg.host_config, NotSet)

    def test_merge_with_config(self):
        cfg = self.sample_map.get_existing('abstract_config')
        merge_cfg = self.sample_map.get_existing('server')
        cfg.merge(merge_cfg)
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, ['app_log', 'server_log'])
        self.assertEqual(cfg.user, 'server_user')
        self.assertEqual(cfg.exposes, [PortBinding(8443, 8443, 'private', False)])
        self.assertEqual(cfg.links, [ContainerLink('svc', 'svc_alias1'), ContainerLink('svc', 'svc_alias2')])
        self.assertEqual(cfg.create_options, {
            'mem_limit': '1g',
            'cpu_shares': 15,
        })
        self.assertEqual(cfg.host_config, {
            'restart_policy': {
                'MaximumRetryCount': 3,
                'Name': 'always',
            },
        })

    def test_merge_with_config_lists_only(self):
        cfg = self.sample_map.get_existing('abstract_config')
        merge_cfg = self.sample_map.get_existing('server')
        cfg.merge(merge_cfg, lists_only=True)
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, ['app_log', 'server_log'])
        self.assertEqual(cfg.user, 'app_user')
        self.assertEqual(cfg.exposes, [PortBinding(8443, 8443, 'private', False)])
        self.assertEqual(cfg.links, [ContainerLink('svc', 'svc_alias1'), ContainerLink('svc', 'svc_alias2')])
        self.assertIs(cfg.create_options, NotSet)
        self.assertIs(cfg.host_config, NotSet)

    def test_extended_config(self):
        cfg = self.ext_main.get_existing('server')
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, ['app_log', 'server_log'])
        self.assertEqual(cfg.user, 'server_user')
        self.assertEqual(cfg.exposes, [PortBinding(8443, 8443, 'private', False)])
        self.assertEqual(cfg.links, [ContainerLink('svc', 'svc_alias1'), ContainerLink('svc', 'svc_alias2')])
        self.assertEqual(cfg.create_options, {
            'mem_limit': '1g',
            'cpu_shares': 15,
        })
        self.assertEqual(cfg.host_config, {
            'restart_policy': {
                'MaximumRetryCount': 3,
                'Name': 'always',
            },
        })

    def test_more_extended_config(self):
        cfg1_1 = self.sample_map.get_existing('worker')
        cfg1 = self.sample_map.get_extended(cfg1_1)
        self.assertEqual(cfg1.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg1.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg1.attaches, ['app_log'])
        self.assertEqual(cfg1.user, 'app_user')
        self.assertEqual(cfg1.create_options, {
            'mem_limit': '2g',
            'cpu_shares': 10,
            'entrypoint': 'celery',
            'command': 'worker -A MyApp -Q queue1,queue2',
        })
        self.assertEqual(cfg1.host_config, {
            'restart_policy': {
                'MaximumRetryCount': 0,
                'Name': 'always',
            },
        })
        cfg2 = self.ext_main.get_existing('worker_q2')
        self.assertEqual(cfg2.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg2.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg2.attaches, ['app_log'])
        self.assertEqual(cfg2.user, 'app_user')
        self.assertEqual(cfg2.create_options, {
            'mem_limit': '1g',
            'cpu_shares': 30,
            'entrypoint': 'celery',
            'command': 'worker -A MyApp -Q queue2',
        })
        self.assertEqual(cfg2.host_config, {
            'restart_policy': {
                'MaximumRetryCount': 0,
                'Name': 'always',
            },
        })

    def test_partial_extended_map(self):
        self.assertEqual(self.ext_simple.host.root, MAP_DATA_3.get('host_root'))

    def test_get_persistent(self):
        attached_items, persistent_items = self.ext_main.get_persistent_items()
        self.assertItemsEqual(attached_items, [('worker', 'app_log'),
                                               ('server', 'app_log'),
                                               ('server', 'server_log'),
                                               ('redis', 'redis_socket'),
                                               ('redis', 'redis_log'),
                                               ('worker_q2', 'app_log')])
        self.assertItemsEqual(persistent_items, [('persistent_one', None)])
