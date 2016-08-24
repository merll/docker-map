# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from collections import namedtuple
import unittest
from six import text_type

from dockermap.functional import lazy, register_type, uses_type_registry, LazyOnceObject, resolve_value, resolve_deep

LOOKUP_DICT = {
    'a': '/test/path_a',
    'b': '/test/path_b',
    'c': ('test_value', 1),
    'd': {
        'd1': 'test_value_1',
        'd2': 'test_value_2',
    },
}


class LazyAccessCounting(LazyOnceObject):
    def __init__(self, func, *args, **kwargs):
        self._actual_func = func
        super(LazyAccessCounting, self).__init__(self._count_proxy, *args, **kwargs)
        self._run_function_count = 0

    def _count_proxy(self, *args, **kwargs):
        self._run_function_count += 1
        return self._actual_func(*args, **kwargs)

    @property
    def run_function_count(self):
        return self._run_function_count


lazy_once = LazyAccessCounting

CustomType = namedtuple('CustomType', ['arg1', 'arg2'])


def resolve_custom(custom_type):
    return LOOKUP_DICT.get(custom_type.arg1, {}).get(custom_type.arg2)


register_type(CustomType, resolve_custom)


class LazyValueResolutionTest(unittest.TestCase):
    def test_simple_lazy_lookup(self):
        a = lazy(LOOKUP_DICT.get, 'a')
        a_val = '/test/path_a'
        self.assertTrue(a == a_val)
        self.assertEqual(a, a_val)
        self.assertEqual(a.get(), a_val)
        self.assertEqual(a.value, a_val)

    def test_lazy_lookup_only_once(self):
        b = lazy_once(LOOKUP_DICT.get, 'b')
        self.assertFalse(b.evaluated)
        b_val = '/test/path_b'
        self.assertEqual(b, b_val)
        self.assertTrue(b.evaluated)
        self.assertTrue(b == b_val)
        self.assertEqual(b.get(), b_val)
        self.assertEqual(b.value, b_val)
        self.assertEqual(b.run_function_count, 1)

    def test_is_type_registered(self):
        ct = CustomType('d', 'd1')
        self.assertTrue(uses_type_registry(ct))

    def test_resolve_lazy_once(self):
        l = lazy_once(LOOKUP_DICT.get, 'c')
        l_val = ('test_value', 1)
        self.assertEqual(resolve_value(l), l_val)
        self.assertEqual(len(resolve_value(l)), 2)
        self.assertEqual(l.run_function_count, 1)

    def test_resolve_custom_type(self):
        ct = CustomType('d', 'd1')
        self.assertEqual(resolve_value(ct), 'test_value_1')

    def test_resolve_deep(self):
        res_data = {
            'a': lazy_once(LOOKUP_DICT.get, 'a'),
            'b': CustomType('d', 'd2'),
            'c': {
                'a': lazy_once(LOOKUP_DICT.get, 'a'),
                'b': lazy_once(LOOKUP_DICT.get, 'b'),
            },
            'd': [
                lazy_once(LOOKUP_DICT.get, 'a'),
                'b',
                {
                    'a': lazy_once(LOOKUP_DICT.get, 'a'),
                    'b': lazy_once(LOOKUP_DICT.get, 'b'),
                },
                lazy_once(LOOKUP_DICT.get, 'd'),
            ],
            CustomType('d', 'd2'): 'e',
        }

        data = resolve_deep(res_data, max_depth=2)
        # Original structures should be preserved
        self.assertIsInstance(data['a'], text_type)
        self.assertIsInstance(data['d'], list)
        self.assertIsInstance(data['d'][2], dict)
        # Nested dictionary should be resolved.
        self.assertEqual(data['c'], dict(a='/test/path_a', b='/test/path_b'))
        self.assertEqual(data['d'][3], dict(d1='test_value_1', d2='test_value_2'))
        # Values below max_depth should not be substituted or evaluated.
        self.assertIsInstance(data['d'][2]['a'], lazy_once)
        self.assertFalse(data['d'][2]['a'].evaluated)
        # Placing functions as dictionary keys may not be a good idea, but should work at least for tuples.
        self.assertEqual(data.get('test_value_2'), 'e')
