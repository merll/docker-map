# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest

import six

from dockermap.map.config.main import ContainerMap
from dockermap.map.input import SharedVolume, PortBinding, ContainerLink, UsedVolume
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
        self.assertEqual(cfg.attaches, [SharedVolume('app_log')])
        self.assertEqual(cfg.user, 'app_user')
        self.assertEqual(cfg.permissions, 'u=rwX,g=rX,o=')

    def test_merge_with_dict(self):
        cfg = self.sample_map.get_existing('abstract_config').copy()
        merge_dict = MAP_DATA_2['containers']['server']
        cfg.merge(merge_dict)
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, [SharedVolume('app_log'), SharedVolume('server_log')])
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
        cfg = self.sample_map.get_existing('abstract_config').copy()
        merge_dict = MAP_DATA_2['containers']['server']
        cfg.merge(merge_dict, lists_only=True)
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, [SharedVolume('app_log'), SharedVolume('server_log')])
        self.assertEqual(cfg.user, 'app_user')
        self.assertEqual(cfg.exposes, [PortBinding(8443, 8443, 'private', False)])
        self.assertEqual(cfg.links, [ContainerLink('svc', 'svc_alias1'), ContainerLink('svc', 'svc_alias2')])
        self.assertDictEqual(cfg.create_options, {})
        self.assertDictEqual(cfg.host_config, {})

    def test_merge_with_config(self):
        cfg = self.sample_map.get_existing('abstract_config').copy()
        merge_cfg = self.sample_map.get_existing('server')
        cfg.merge(merge_cfg)
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, [SharedVolume('app_log'), SharedVolume('server_log')])
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
        cfg = self.sample_map.get_existing('abstract_config').copy()
        merge_cfg = self.sample_map.get_existing('server')
        cfg.merge(merge_cfg, lists_only=True)
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, [SharedVolume('app_log'), SharedVolume('server_log')])
        self.assertEqual(cfg.user, 'app_user')
        self.assertEqual(cfg.exposes, [PortBinding(8443, 8443, 'private', False)])
        self.assertEqual(cfg.links, [ContainerLink('svc', 'svc_alias1'), ContainerLink('svc', 'svc_alias2')])
        self.assertDictEqual(cfg.create_options, {})
        self.assertDictEqual(cfg.host_config, {})

    def test_extended_config(self):
        cfg = self.ext_main.get_existing('server')
        self.assertEqual(cfg.binds, [SharedVolume('app_config', True), SharedVolume('app_data', False)])
        self.assertEqual(cfg.uses, [SharedVolume('redis.redis_socket', False)])
        self.assertEqual(cfg.attaches, [SharedVolume('app_log'), SharedVolume('server_log')])
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
        self.assertEqual(cfg1.attaches, [SharedVolume('app_log')])
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
        self.assertEqual(cfg2.attaches, [SharedVolume('app_log')])
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
        six.assertCountEqual(self, attached_items, [('worker', SharedVolume('app_log')),
                                                    ('server', SharedVolume('app_log')),
                                                    ('server', SharedVolume('server_log')),
                                                    ('server2', SharedVolume('app_log')),
                                                    ('server2', SharedVolume('server_log')),
                                                    ('redis', SharedVolume('redis_socket')),
                                                    ('redis', UsedVolume('redis_log', '/var/log/redis')),
                                                    ('worker_q2', SharedVolume('app_log'))])
        six.assertCountEqual(self, persistent_items, [('persistent_one', None)])

    def test_serialization(self):
        sd1 = self.sample_map.as_dict()
        m1_1 = ContainerMap('main', sd1)
        self.assertEqual(m1_1, self.sample_map)
        sd1_2 = ContainerMap('main_1', sd1)
        self.assertNotEqual(sd1_2, self.sample_map)
        sd2 = m1_1.as_dict()
        self.assertEqual(sd1, sd2)

    def test_serialization_extended(self):
        sd2 = self.ext_main.as_dict()
        m2_1 = ContainerMap('main', sd2)
        self.assertNotEqual(m2_1, self.ext_main)
        m2_2 = m2_1.get_extended_map()
        self.assertEqual(m2_2, self.ext_main)
        self.assertEqual(m2_1.as_dict(), sd2)
        self.assertEqual(m2_2.as_dict(), sd2)
