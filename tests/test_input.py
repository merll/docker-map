# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest
import six

from dockermap.functional import lazy_once
from dockermap.utils import merge_list
from dockermap.map.config.main import ContainerMap
from dockermap.map.config.utils import expand_groups, get_map_config_ids
from dockermap.map.input import (is_path, read_only, get_list,
                                 get_shared_host_volume, get_shared_host_volumes, SharedVolume,
                                 get_container_link, get_container_links, ContainerLink,
                                 get_port_binding, get_port_bindings, PortBinding,
                                 get_exec_command, get_exec_commands, ExecCommand, ExecPolicy,
                                 get_input_config_id, get_input_config_ids, MapConfigId,
                                 ItemType, NetworkEndpoint, get_network_endpoint, get_network_endpoints, HostVolume,
                                 get_attached_volume, UsedVolume, get_attached_volumes, InputConfigId)


class InputConversionTest(unittest.TestCase):
    def test_is_path(self):
        self.assertFalse(is_path(None))
        self.assertFalse(is_path(''))
        self.assertFalse(is_path('.'))
        self.assertFalse(is_path('test'))
        self.assertTrue(is_path('/'))
        self.assertTrue(is_path('/test'))
        self.assertTrue(is_path('./'))
        self.assertTrue(is_path('./test'))

    def test_read_only(self):
        self.assertFalse(read_only(None))
        self.assertFalse(read_only(''))
        self.assertFalse(read_only(0))
        self.assertFalse(read_only('rw'))
        self.assertTrue(read_only('ro'))
        self.assertTrue(read_only(1))
        self.assertTrue(read_only('test'))

    def test_get_list(self):
        self.assertEqual(get_list(()), [])
        self.assertEqual(get_list(None), [])
        self.assertEqual(get_list(lazy_once(lambda: 'test')), ['test'])
        self.assertEqual(get_list('test'), ['test'])

    def test_get_shared_host_volume(self):
        assert_a = lambda a: self.assertEqual(get_shared_host_volume(a), SharedVolume('a', False))
        assert_b = lambda b: self.assertEqual(get_shared_host_volume(b), SharedVolume('b', True))
        assert_c = lambda c: self.assertEqual(get_shared_host_volume(c), HostVolume('ch', 'c', False))
        assert_d = lambda d: self.assertEqual(get_shared_host_volume(d), HostVolume('dh', 'd', True))

        assert_a('a')
        assert_a(('a', ))
        assert_a(['a', False])
        assert_b(SharedVolume('b', True))
        assert_b(('b', 'ro'))
        assert_b({'b': 'ro'})
        assert_c(('c', 'ch'))
        assert_c(('c', 'ch', False))
        assert_c(('c', ['ch']))
        assert_c(('c', ('ch', 'rw')))
        assert_c({'c': 'ch'})
        assert_c({'c': ('ch', )})
        assert_d(('d', 'dh', 'ro'))
        assert_d({'d': ('dh', True)})

    def test_get_shared_host_volumes(self):
        assert_a = lambda a: self.assertEqual(get_shared_host_volumes(a), [SharedVolume('a', False)])
        assert_b = lambda b: six.assertCountEqual(self, get_shared_host_volumes(b), [SharedVolume('a', False),
                                                                                     SharedVolume('b', True),
                                                                                     HostVolume('ch', 'c', False),
                                                                                     HostVolume('dh', 'd', True)])

        assert_a('a')
        assert_a([('a', )])
        assert_a((['a', False], ))
        assert_b([['a'], SharedVolume('b', True), ('c', 'ch'), ('d', 'dh', 'ro')])
        assert_b(['a', ('b', 'ro'), ('c', ['ch']), ('d', 'dh', True)])
        assert_b({'a': False, 'b': 'ro', 'c': 'ch', 'd': ('dh', True)})

    def test_get_attached_volume(self):
        assert_a = lambda a: self.assertEqual(get_attached_volume(a), SharedVolume('a', False))
        assert_c = lambda c: self.assertEqual(get_attached_volume(c), UsedVolume('c', 'p1', False))

        assert_a(SharedVolume('a', False))
        assert_a('a')
        assert_a(('a', ))
        assert_c(UsedVolume('c', 'p1'))
        assert_c(('c', 'p1'))
        assert_c({'c': 'p1'})

    def test_get_attached_volumes(self):
        assert_a = lambda a: self.assertEqual(get_attached_volumes(a), [SharedVolume('a', False)])
        assert_b = lambda b: six.assertCountEqual(self, get_attached_volumes(b), [SharedVolume('a', False),
                                                                                  SharedVolume('b', False),
                                                                                  UsedVolume('c', 'p1', False)])

        assert_a(SharedVolume('a', False))
        assert_a('a')
        assert_a(('a', ))
        assert_b(['a', ('b', False), {'c': 'p1'}])
        assert_b({'a': False, 'b': None, 'c': 'p1'})

    def test_get_used_volume(self):
        pass

    def test_get_used_volumes(self):
        pass

    def test_get_container_link(self):
        assert_a = lambda a: self.assertEqual(get_container_link(a), ContainerLink('a', None))
        assert_b = lambda b: self.assertEqual(get_container_link(b), ContainerLink('b', 'b_'))

        assert_a('a')
        assert_a(('a', ))
        assert_a(['a', None])
        assert_b(('b', 'b_'))

    def test_get_container_links(self):
        assert_a = lambda a: self.assertEqual(get_container_links(a), [ContainerLink('a', None)])
        assert_b = lambda b: six.assertCountEqual(self, get_container_links(b), [ContainerLink('a', None),
                                                                                 ContainerLink('b', 'b_')])

        assert_a('a')
        assert_a((ContainerLink('a'), ))
        assert_a([('a', )])
        assert_b(('a', ('b', 'b_')))
        assert_b({'a': None, 'b': 'b_'})

    def test_get_port_binding(self):
        assert_a = lambda a: self.assertEqual(get_port_binding(a), PortBinding('1234'))
        assert_b = lambda b: self.assertEqual(get_port_binding(b), PortBinding(1234, 1234))
        assert_c = lambda c: self.assertEqual(get_port_binding(c), PortBinding(1234, 1234, '0.0.0.0'))
        assert_d = lambda d: self.assertEqual(get_port_binding(d), PortBinding(1234, 1234, '0.0.0.0', True))

        assert_a('1234')
        assert_a(('1234', ))
        assert_a(['1234', None])
        assert_a({'exposed_port': '1234'})
        assert_b((1234, lazy_once(lambda: 1234)))
        assert_c((1234, 1234, '0.0.0.0'))
        assert_c((1234, [1234, '0.0.0.0']))
        assert_d((1234, 1234, '0.0.0.0', True))
        assert_d(dict(exposed_port=1234, host_port=1234, interface='0.0.0.0', ipv6=True))
        assert_d((1234, [1234, '0.0.0.0', True]))

    def test_get_port_bindings(self):
        assert_a = lambda a: self.assertEqual(get_port_bindings(a), [PortBinding('1234')])
        assert_b = lambda b: six.assertCountEqual(self, get_port_bindings(b), [PortBinding('1234'),
                                                                               PortBinding(1234, 1234),
                                                                               PortBinding(1235, 1235, '0.0.0.0', True)])

        assert_a('1234')
        assert_a(PortBinding('1234', None, None, False))
        assert_a((['1234'], ))
        assert_b(['1234', (1234, 1234), (1235, 1235, '0.0.0.0', True)])
        assert_b([('1234', [None, None]), PortBinding(1234, 1234), (1235, [1235, '0.0.0.0', True])])
        assert_b({'1234': None, 1234: 1234, 1235: (1235, '0.0.0.0', True)})
        assert_b({'1234': None, 1234: dict(host_port=1234), 1235: dict(host_port=1235, interface='0.0.0.0', ipv6=True)})

    def test_get_exec_command(self):
        assert_a = lambda a: self.assertEqual(get_exec_command(a),
                                              ExecCommand('a b c', None, ExecPolicy.RESTART))
        assert_b = lambda b: self.assertEqual(get_exec_command(b),
                                              ExecCommand(['a', 'b', 'c'], None, ExecPolicy.RESTART))
        assert_c = lambda c: self.assertEqual(get_exec_command(c),
                                              ExecCommand('a b c', 'user', ExecPolicy.RESTART))
        assert_d = lambda d: self.assertEqual(get_exec_command(d),
                                              ExecCommand(['a', 'b', 'c'], 'user', ExecPolicy.RESTART))
        assert_e = lambda e: self.assertEqual(get_exec_command(e),
                                              ExecCommand('a b c', 'user', ExecPolicy.INITIAL))
        assert_f = lambda f: self.assertEqual(get_exec_command(f),
                                              ExecCommand(['a', 'b', 'c'], 'user', ExecPolicy.INITIAL))

        assert_a('a b c')
        assert_a(('a b c', ))
        assert_a(['a b c', None])
        assert_a(lazy_once(lambda: 'a b c'))
        assert_b((['a', 'b', 'c'],))
        assert_b([['a', 'b', 'c'], None])
        assert_c(('a b c', 'user'))
        assert_c([lazy_once(lambda: 'a b c'), lazy_once(lambda: 'user')])
        assert_d((['a', 'b', 'c'], 'user'))
        assert_d([lazy_once(lambda: ['a', 'b', 'c']), lazy_once(lambda: 'user')])
        assert_e(('a b c', 'user', ExecPolicy.INITIAL))
        assert_e([lazy_once(lambda: 'a b c'), lazy_once(lambda: 'user'), ExecPolicy.INITIAL])
        assert_f((['a', 'b', 'c'], 'user', ExecPolicy.INITIAL))
        assert_f([lazy_once(lambda: ['a', 'b', 'c']), lazy_once(lambda: 'user'), ExecPolicy.INITIAL])

    def test_get_exec_commmands(self):
        assert_a = lambda a: self.assertEqual(get_exec_commands(a), [ExecCommand('a b c', None, ExecPolicy.RESTART)])
        assert_b = lambda b: six.assertCountEqual(self, get_exec_commands(b),
                                                  [ExecCommand(['a', 'b', 'c'], None, ExecPolicy.RESTART),
                                                   ExecCommand('a b c', 'user', ExecPolicy.RESTART),
                                                   ExecCommand(['a', 'b', 'c'], 'root', ExecPolicy.INITIAL)])
        assert_a('a b c')
        assert_a([ExecCommand('a b c', None, ExecPolicy.RESTART)])
        assert_a(['a b c'])
        assert_b([(['a', 'b', 'c', ],), ('a b c', 'user'), [['a', 'b', 'c', ], 'root', ExecPolicy.INITIAL]])
        assert_b([(['a', 'b', 'c'], None),
                  ExecCommand('a b c', 'user', ExecPolicy.RESTART),
                  [['a', 'b', 'c'], 'root', ExecPolicy.INITIAL]])

    def test_get_network_endpoint(self):
        assert_e1 = lambda v: self.assertEqual(get_network_endpoint(v), NetworkEndpoint('endpoint1'))
        assert_e2 = lambda v: self.assertEqual(get_network_endpoint(v), NetworkEndpoint('endpoint2', ['alias1']))
        assert_e3 = lambda v: self.assertEqual(get_network_endpoint(v),
                                               NetworkEndpoint('endpoint3', ['alias1'], ipv4_address='0.0.0.0'))
        assert_e1('endpoint1')
        assert_e1(['endpoint1'])
        assert_e1({'endpoint1': ''})
        assert_e2(['endpoint2', 'alias1'])
        assert_e2({'endpoint2': 'alias1'})
        assert_e2(['endpoint2', dict(aliases='alias1')])
        assert_e2(['endpoint2', ('alias1', )])
        assert_e2({'endpoint2': 'alias1'})
        assert_e2({'endpoint2': ('alias1', )})
        assert_e2({'endpoint2': dict(aliases='alias1')})
        assert_e2({'endpoint2': dict(aliases=('alias1', ))})
        assert_e3(['endpoint3', 'alias1', None, '0.0.0.0'])
        assert_e3({'endpoint3': ('alias1', None, '0.0.0.0')})
        assert_e3(['endpoint3', dict(aliases='alias1', ipv4_address='0.0.0.0')])
        assert_e3({'endpoint3': dict(aliases='alias1', ipv4_address='0.0.0.0')})

    def test_get_network_endpoints(self):
        assert_e1 = lambda v: self.assertEqual(get_network_endpoints(v), [NetworkEndpoint('endpoint1')])
        assert_e2 = lambda v: six.assertCountEqual(self, get_network_endpoints(v),
                                                   [NetworkEndpoint('endpoint2', ['alias1']),
                                                    NetworkEndpoint('endpoint3', ['alias1'], ipv4_address='0.0.0.0')])
        assert_e1('endpoint1')
        assert_e1(['endpoint1'])
        assert_e1({'endpoint1': None})
        assert_e2([
            ('endpoint2', 'alias1'),
            ['endpoint3', 'alias1', None, '0.0.0.0'],
        ])
        assert_e2([
            ('endpoint2', 'alias1'),
            ['endpoint3', 'alias1', None, '0.0.0.0'],
        ])
        assert_e2([
            ('endpoint2', dict(aliases='alias1')),
            ['endpoint3', dict(aliases=('alias1', ), ipv4_address='0.0.0.0')],
        ])

    def test_get_input_config_id(self):
        assert_a = lambda v, m=None, i=None: self.assertEqual(get_input_config_id(v, map_name=m, instances=i),
                                                              InputConfigId(ItemType.CONTAINER, 'm', 'c'))
        assert_b = lambda v, m=None, i=None: self.assertEqual(get_input_config_id(v, map_name=m, instances=i),
                                                              InputConfigId(ItemType.CONTAINER, 'm', 'c', ('i', )))
        assert_c = lambda v, m=None, i=None: self.assertEqual(get_input_config_id(v, map_name=m, instances=i),
                                                              InputConfigId(ItemType.CONTAINER, 'm', 'c', ('i', 'j')))
        assert_a('m.c')
        assert_a('m.c', 'x')
        assert_a('m.c.')
        assert_a(('m', 'c', None))
        assert_a(['m', 'c'])
        assert_a(['m', 'c', []], 'x')
        assert_a('c', 'm')
        assert_a(['c'], 'm')
        assert_b('m.c.i')
        assert_b('m.c.i', 'x', 'j')
        assert_b(('m', 'c', 'i'))
        assert_b(['m', 'c', 'i'])
        assert_b(['m', 'c', ('i', )])
        assert_b(('m', 'c', ('i', )))
        assert_b(('m', 'c'), i=('i', ))
        assert_b('c', 'm', ('i', ))
        assert_b(('c', ), 'm', ('i', ))
        assert_c(['m', 'c', ('i', 'j')])
        assert_c(('m', 'c', ['i', 'j']))
        assert_c(('m', 'c'), i=('i', 'j'))
        assert_c('c', 'm', ('i', 'j'))
        assert_c(('c', ), 'm', ('i', 'j'))

    def test_get_input_config_ids(self):
        map_m = ContainerMap('m', c=dict(instances=['i']), d=dict(instances=['i']), groups=dict(default=['c.i', 'd.i']))
        map_n = ContainerMap('n', e={}, groups=dict(default=['e']))
        maps = {'m': map_m, 'n': map_n}

        def assert_a(v, m=None, i=None):
            self.assertEqual(get_input_config_ids(v, map_name=m, instances=i),
                             [InputConfigId(ItemType.CONTAINER, 'm', 'c')])
            self.assertEqual(get_map_config_ids(v, maps, default_map_name=m, default_instances=i),
                             [MapConfigId(ItemType.CONTAINER, 'm', 'c', 'i')])

        def assert_b(v, m=None, i=None):
            six.assertCountEqual(self, get_input_config_ids(v, map_name=m, instances=i),
                                 [InputConfigId(ItemType.CONTAINER, 'm', 'c', ('i', )),
                                  InputConfigId(ItemType.CONTAINER, 'm', 'd', ('i', )),
                                  InputConfigId(ItemType.CONTAINER, 'n', 'e', ('i', 'j'))])
            six.assertCountEqual(self, get_map_config_ids(v, maps, default_map_name=m, default_instances=i),
                                 [MapConfigId(ItemType.CONTAINER, 'm', 'c', 'i'),
                                  MapConfigId(ItemType.CONTAINER, 'm', 'd', 'i'),
                                  MapConfigId(ItemType.CONTAINER, 'n', 'e', 'i'),
                                  MapConfigId(ItemType.CONTAINER, 'n', 'e', 'j')])

        def assert_c(v, m=None, i=None):
            six.assertCountEqual(self, expand_groups(get_input_config_ids(v, map_name=m, instances=i), maps),
                                 [InputConfigId(ItemType.CONTAINER, 'm', 'c', ('i', )),
                                  InputConfigId(ItemType.CONTAINER, 'm', 'd', ('i', )),
                                  InputConfigId(ItemType.CONTAINER, 'n', 'e', ('i', )),
                                  InputConfigId(ItemType.CONTAINER, 'n', 'e', ('j', ))])
            six.assertCountEqual(self, get_map_config_ids(v, maps, default_map_name=m, default_instances=i),
                                 [MapConfigId(ItemType.CONTAINER, 'm', 'c', 'i'),
                                  MapConfigId(ItemType.CONTAINER, 'm', 'd', 'i'),
                                  MapConfigId(ItemType.CONTAINER, 'n', 'e', 'i'),
                                  MapConfigId(ItemType.CONTAINER, 'n', 'e', 'j')])

        assert_a('m.c')
        assert_a('c', 'm')
        assert_a('c', 'm', [])
        assert_a([['m', 'c']])
        assert_b(['m.c.',
                  'd',
                  ('n', 'e', ['i', 'j'])], 'm', 'i')
        assert_b([[None, 'c'],
                  ('d', ),
                  ['n', 'e', ('i', 'j')]], 'm', ('i',))
        assert_c(['m.default', 'n.default', 'n.e.j'], None, ('i', ))

    def test_get_map_config_ids_all_alias(self):
        map_m = ContainerMap('m', c1=dict(), c2=dict(), c3=dict(), groups=dict(default=['c3']))
        map_n = ContainerMap('n', c1=dict(), c3=dict(), groups=dict(default=['c3']))
        maps = {'m': map_m, 'n': map_n}
        six.assertCountEqual(self, get_map_config_ids('m.__all__', maps),
                             [MapConfigId(ItemType.CONTAINER, 'm', 'c1'),
                              MapConfigId(ItemType.CONTAINER, 'm', 'c2'),
                              MapConfigId(ItemType.CONTAINER, 'm', 'c3')])
        six.assertCountEqual(self, get_map_config_ids('__all__.__all__', maps),
                             [MapConfigId(ItemType.CONTAINER, 'm', 'c1'),
                              MapConfigId(ItemType.CONTAINER, 'm', 'c2'),
                              MapConfigId(ItemType.CONTAINER, 'm', 'c3'),
                              MapConfigId(ItemType.CONTAINER, 'n', 'c1'),
                              MapConfigId(ItemType.CONTAINER, 'n', 'c3')])
        six.assertCountEqual(self, get_map_config_ids('__all__.c1',maps),
                             [MapConfigId(ItemType.CONTAINER, 'm', 'c1'),
                              MapConfigId(ItemType.CONTAINER, 'n', 'c1')])
        six.assertCountEqual(self, get_map_config_ids('__all__.default', maps),
                             [MapConfigId(ItemType.CONTAINER, 'm', 'c3'),
                              MapConfigId(ItemType.CONTAINER, 'n', 'c3')])

    def test_merge_list(self):
        list1 = ['a', 'b', 'c']
        merge_list(list1, ['d'])
        self.assertListEqual(list1, ['a', 'b', 'c', 'd'])
        merge_list(list1, ['c', 'c'])
        self.assertListEqual(list1, ['a', 'b', 'c', 'd'])
