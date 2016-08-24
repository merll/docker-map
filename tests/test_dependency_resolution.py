# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest
import six

from dockermap.api import ContainerMap
from dockermap.client.docker_util import ContainerImageResolver
from dockermap.map.policy.dep import ContainerDependencyResolver


TEST_MAP_DATA = {
    'a': dict(uses=['b', 'c']),
    'b': dict(uses=['dv', 'f'], links='e.1'),
    'c': dict(),
    'd': dict(uses='e', instances=['1', '2'], attaches='dv'),
    'e': dict(instances=['1', '2']),
    'f': dict(),
    'l': dict(links='e.1'),
    'x': dict(uses=['b', 'f']),
}

TEST_IMG_DATA = [
    ('a', 'b'),
    ('b', 'c'),
    ('c', 'e'),
    ('d', 'e'),
    ('f', 'x'),
]
TEST_CONTAINER_IMAGES = {'a', 'c', 'f'}


class ContainerDependencyTest(unittest.TestCase):
    def setUp(self):
        test_map = ContainerMap('test_map', initial=TEST_MAP_DATA, check_integrity=False)
        self.f_res = ContainerDependencyResolver()
        self.f_res.update(test_map.dependency_items())
        self.r_res = ContainerDependencyResolver()
        self.r_res.update_backward(test_map.dependency_items(reverse=True))

    def assertOrder(self, dependency_list, *items):
        iterator = iter(items)
        last_item = six.next(iterator)
        last_idx = dependency_list.index(last_item)
        for item in iterator:
            index = dependency_list.index(item)
            if index < last_idx:
                self.fail("{0} found before {1}, should be later.".format(item, last_item))

    def test_forward_resolution_order(self):
        a_dep = self.f_res.get_dependencies(('test_map', 'a'))
        self.assertOrder(a_dep,
                         ('test_map', 'd', [None]),
                         ('test_map', 'b', [None]))
        self.assertOrder(a_dep,
                         ('test_map', 'e', [None]),
                         ('test_map', 'd', [None]))
        self.assertOrder(a_dep,
                         ('test_map', 'e', [None]),
                         ('test_map', 'b', [None]))
        self.assertOrder(a_dep,
                         ('test_map', 'f', [None]),
                         ('test_map', 'b', [None]))
        self.assertNotIn(('test_map', 'e', ['1']), a_dep)
        l_dep = self.f_res.get_dependencies(('test_map', 'l'))
        self.assertListEqual(l_dep, [('test_map', 'e', ['1'])])
        x_dep = self.f_res.get_dependencies(('test_map', 'x'))
        self.assertOrder(x_dep,
                         ('test_map', 'f', [None]),
                         ('test_map', 'b', [None]))

    def test_backward_resolution_order(self):
        f_dep = self.r_res.get_dependencies(('test_map', 'f'))
        self.assertOrder(f_dep,
                         ('test_map', 'x', [None]),
                         ('test_map', 'b', [None]))
        self.assertOrder(f_dep,
                         ('test_map', 'a', [None]),
                         ('test_map', 'b', [None]))
        e_dep = self.r_res.get_dependencies(('test_map', 'e'))
        self.assertOrder(e_dep,
                         ('test_map', 'a', [None]),
                         ('test_map', 'b', [None]),
                         ('test_map', 'd', [None]))


class ImageDependencyTest(unittest.TestCase):
    def setUp(self):
        self.res = ContainerImageResolver(TEST_CONTAINER_IMAGES, TEST_IMG_DATA)

    def test_image_dependencies(self):
        self.assertTrue(self.res.get_dependencies('a'))
        self.assertTrue(self.res.get_dependencies('b'))
        self.assertTrue(self.res.get_dependencies('c'))
        self.assertTrue(self.res.get_dependencies('f'))
        self.assertFalse(self.res.get_dependencies('d'))
        self.assertFalse(self.res.get_dependencies('e'))
        self.assertFalse(self.res.get_dependencies('x'))


if __name__ == '__main__':
    unittest.main()
