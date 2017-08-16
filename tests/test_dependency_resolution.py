# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest
import six

from dockermap.api import ContainerMap
from dockermap.map.input import ItemType
from dockermap.dep import ImageDependentsResolver
from dockermap.map.policy.dep import ContainerDependencyResolver, ContainerDependentsResolver


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


class ContainerDependencyTest(unittest.TestCase):
    def setUp(self):
        test_map = ContainerMap('test_map', initial=TEST_MAP_DATA, check_integrity=False)
        dependency_items = list(test_map.dependency_items())
        self.f_res = ContainerDependencyResolver(dependency_items)
        self.r_res = ContainerDependentsResolver(dependency_items)

    def assertOrder(self, dependency_list, *items):
        iterator = iter(items)
        last_item = six.next(iterator)
        last_idx = dependency_list.index(last_item)
        for item in iterator:
            index = dependency_list.index(item)
            if index < last_idx:
                self.fail("{0} found before {1}, should be later.".format(item, last_item))

    def test_forward_resolution_order(self):
        a_dep = self.f_res.get_dependencies((ItemType.CONTAINER, 'test_map', 'a', None))
        self.assertOrder(a_dep,
                         (ItemType.VOLUME, 'test_map', 'd', 'dv'),
                         (ItemType.CONTAINER, 'test_map', 'd', '1'),
                         (ItemType.CONTAINER, 'test_map', 'd', '2'),
                         (ItemType.CONTAINER, 'test_map', 'b', None))
        self.assertOrder(a_dep,
                         (ItemType.CONTAINER, 'test_map', 'e', '1'),
                         (ItemType.CONTAINER, 'test_map', 'e', '2'),
                         (ItemType.CONTAINER, 'test_map', 'd', '1'),
                         (ItemType.CONTAINER, 'test_map', 'd', '2'))
        self.assertOrder(a_dep,
                         (ItemType.CONTAINER, 'test_map', 'e', '1'),
                         (ItemType.CONTAINER, 'test_map', 'e', '2'),
                         (ItemType.CONTAINER, 'test_map', 'b', None))
        self.assertOrder(a_dep,
                         (ItemType.CONTAINER, 'test_map', 'f', None),
                         (ItemType.CONTAINER, 'test_map', 'b', None))
        l_dep = self.f_res.get_dependencies((ItemType.CONTAINER, 'test_map', 'l', None))
        self.assertListEqual(l_dep, [
            (ItemType.IMAGE, 'test_map', 'e', 'latest'),
            (ItemType.CONTAINER, 'test_map', 'e', '1'),
            (ItemType.IMAGE, 'test_map', 'l', 'latest'),
        ])
        x_dep = self.f_res.get_dependencies((ItemType.CONTAINER, 'test_map', 'x', None))
        self.assertOrder(x_dep,
                         (ItemType.CONTAINER, 'test_map', 'f', None),
                         (ItemType.CONTAINER, 'test_map', 'b', None))

    def test_backward_resolution_order(self):
        f_dep = self.r_res.get_dependencies((ItemType.CONTAINER, 'test_map', 'f', None))
        self.assertOrder(f_dep,
                         (ItemType.CONTAINER, 'test_map', 'x', None),
                         (ItemType.CONTAINER, 'test_map', 'b', None))
        self.assertOrder(f_dep,
                         (ItemType.CONTAINER, 'test_map', 'a', None),
                         (ItemType.CONTAINER, 'test_map', 'b', None))
        e_dep = self.r_res.get_dependencies((ItemType.CONTAINER, 'test_map', 'e', '1'))
        self.assertOrder(e_dep,
                         (ItemType.CONTAINER, 'test_map', 'a', None),
                         (ItemType.CONTAINER, 'test_map', 'b', None),
                         (ItemType.CONTAINER, 'test_map', 'd', '1'),
                         (ItemType.CONTAINER, 'test_map', 'd', '2'))


class ImageDependenceTest(unittest.TestCase):
    def setUp(self):
        self.res = ImageDependentsResolver(TEST_IMG_DATA)

    def test_image_dependencies(self):
        self.assertListEqual([], self.res.get_dependencies('a'))
        self.assertListEqual(['a'], self.res.get_dependencies('b'))
        self.assertListEqual(['a', 'b'], self.res.get_dependencies('c'))
        self.assertListEqual(['a', 'b', 'c', 'd'], self.res.get_dependencies('e'))
        self.assertListEqual(['f'], self.res.get_dependencies('x'))


if __name__ == '__main__':
    unittest.main()
