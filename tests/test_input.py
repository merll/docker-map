# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest
import six

from dockermap.functional import lazy_once
from dockermap.map.input import (is_path, read_only, get_list, get_shared_volume, get_shared_volumes,
                                 get_shared_host_volume, get_shared_host_volumes, SharedVolume,
                                 get_container_link, get_container_links, ContainerLink,
                                 get_port_binding, get_port_bindings, PortBinding,
                                 get_exec_command, get_exec_commands, ExecCommand, EXEC_POLICY_RESTART, EXEC_POLICY_INITIAL)


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

    def test_get_shared_volume(self):
        assert_a = lambda a: self.assertEqual(get_shared_volume(a), SharedVolume('a', False))
        assert_b = lambda b: self.assertEqual(get_shared_volume(b), SharedVolume('b', True))

        assert_a(SharedVolume('a', False))
        assert_a('a')
        assert_a(('a', ))
        assert_b(('b', 'true'))
        assert_b({'b': 'true'})

    def test_get_shared_volumes(self):
        assert_a = lambda a: self.assertEqual(get_shared_volumes(a), [SharedVolume('a', False)])
        assert_b = lambda b: six.assertCountEqual(self, get_shared_volumes(b), [SharedVolume('a', False),
                                                                                SharedVolume('b', True)])

        assert_a(SharedVolume('a', False))
        assert_a('a')
        assert_a(('a', ))
        assert_a({'a': False})
        assert_b(['a', ('b', 'true')])
        assert_b({'a': False, 'b': 'true'})

    def test_get_shared_host_volume(self):
        assert_a = lambda a: self.assertEqual(get_shared_host_volume(a), SharedVolume('a', False))
        assert_b = lambda b: self.assertEqual(get_shared_host_volume(b), SharedVolume('b', True))
        assert_c = lambda c: self.assertEqual(get_shared_host_volume(c), SharedVolume(('c', 'ch'), False))
        assert_d = lambda d: self.assertEqual(get_shared_host_volume(d), SharedVolume(('d', 'dh'), True))

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
                                                                                     SharedVolume(('c', 'ch'), False),
                                                                                     SharedVolume(('d', 'dh'), True)])

        assert_a('a')
        assert_a([('a', )])
        assert_a((['a', False], ))
        assert_b([['a'], SharedVolume('b', True), ('c', 'ch'), ('d', 'dh', 'ro')])
        assert_b(['a', ('b', 'ro'), ('c', ['ch']), ('d', 'dh', True)])
        assert_b({'a': False, 'b': 'ro', 'c': 'ch', 'd': ('dh', True)})

    def test_get_container_link(self):
        assert_a = lambda a: self.assertEqual(get_container_link(a), ContainerLink('a', 'a'))
        assert_b = lambda b: self.assertEqual(get_container_link(b), ContainerLink('b', 'b_'))

        assert_a('a')
        assert_a(('a', ))
        assert_a(['a', 'a'])
        assert_b(('b', 'b_'))

    def test_get_container_links(self):
        assert_a = lambda a: self.assertEqual(get_container_links(a), [ContainerLink('a', 'a')])
        assert_b = lambda b: six.assertCountEqual(self, get_container_links(b), [ContainerLink('a', 'a'),
                                                                                 ContainerLink('b', 'b_')])

        assert_a('a')
        assert_a((ContainerLink('a', 'a'), ))
        assert_a([('a', )])
        assert_b(('a', ('b', 'b_')))
        assert_b({'a': 'a', 'b': 'b_'})

    def test_get_port_binding(self):
        assert_a = lambda a: self.assertEqual(get_port_binding(a), PortBinding('1234', None, None, False))
        assert_b = lambda b: self.assertEqual(get_port_binding(b), PortBinding(1234, 1234, None, False))
        assert_c = lambda c: self.assertEqual(get_port_binding(c), PortBinding(1234, 1234, '0.0.0.0', False))
        assert_d = lambda d: self.assertEqual(get_port_binding(d), PortBinding(1234, 1234, '0.0.0.0', True))

        assert_a('1234')
        assert_a(('1234', ))
        assert_a(['1234', None])
        assert_b((1234, lazy_once(lambda: 1234)))
        assert_c((1234, 1234, '0.0.0.0'))
        assert_c((1234, [1234, '0.0.0.0']))
        assert_d((1234, 1234, '0.0.0.0', True))
        assert_d((1234, [1234, '0.0.0.0', True]))

    def test_get_port_bindings(self):
        assert_a = lambda a: self.assertEqual(get_port_bindings(a), [PortBinding('1234', None, None, False)])
        assert_b = lambda b: six.assertCountEqual(self, get_port_bindings(b), [PortBinding('1234', None, None, False),
                                                                               PortBinding(1234, 1234, None, False),
                                                                               PortBinding(1235, 1235, '0.0.0.0', True)])

        assert_a('1234')
        assert_a(PortBinding('1234', None, None, False))
        assert_a((['1234'], ))
        assert_b(['1234', (1234, 1234), (1235, 1235, '0.0.0.0', True)])
        assert_b([('1234', [None, None]), PortBinding(1234, 1234, None, False), (1235, [1235, '0.0.0.0', True])])
        assert_b({'1234': None, 1234: 1234, 1235: (1235, '0.0.0.0', True)})

    def test_get_exec_command(self):
        assert_a = lambda a: self.assertEqual(get_exec_command(a),
                                              ExecCommand('a b c', None, EXEC_POLICY_RESTART))
        assert_b = lambda b: self.assertEqual(get_exec_command(b),
                                              ExecCommand(['a', 'b', 'c'], None, EXEC_POLICY_RESTART))
        assert_c = lambda c: self.assertEqual(get_exec_command(c),
                                              ExecCommand('a b c', 'user', EXEC_POLICY_RESTART))
        assert_d = lambda d: self.assertEqual(get_exec_command(d),
                                              ExecCommand(['a', 'b', 'c'], 'user', EXEC_POLICY_RESTART))
        assert_e = lambda e: self.assertEqual(get_exec_command(e),
                                              ExecCommand('a b c', 'user', EXEC_POLICY_INITIAL))
        assert_f = lambda f: self.assertEqual(get_exec_command(f),
                                              ExecCommand(['a', 'b', 'c'], 'user', EXEC_POLICY_INITIAL))

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
        assert_e(('a b c', 'user', EXEC_POLICY_INITIAL))
        assert_e([lazy_once(lambda: 'a b c'), lazy_once(lambda: 'user'), EXEC_POLICY_INITIAL])
        assert_f((['a', 'b', 'c'], 'user', EXEC_POLICY_INITIAL))
        assert_f([lazy_once(lambda: ['a', 'b', 'c']), lazy_once(lambda: 'user'), EXEC_POLICY_INITIAL])

    def test_get_exec_commmands(self):
        assert_a = lambda a: self.assertEqual(get_exec_commands(a), [ExecCommand('a b c', None, EXEC_POLICY_RESTART)])
        assert_b = lambda b: six.assertCountEqual(self, get_exec_commands(b),
                                                  [ExecCommand(['a', 'b', 'c'], None, EXEC_POLICY_RESTART),
                                                   ExecCommand('a b c', 'user', EXEC_POLICY_RESTART),
                                                   ExecCommand(['a', 'b', 'c'], 'root', EXEC_POLICY_INITIAL)])
        assert_a('a b c')
        assert_a([ExecCommand('a b c', None, EXEC_POLICY_RESTART)])
        assert_a(['a b c'])
        assert_b([(['a', 'b', 'c', ],), ('a b c', 'user'), [['a', 'b', 'c', ], 'root', EXEC_POLICY_INITIAL]])
        assert_b([(['a', 'b', 'c'], None),
                  ExecCommand('a b c', 'user', EXEC_POLICY_RESTART),
                  [['a', 'b', 'c'], 'root', EXEC_POLICY_INITIAL]])
