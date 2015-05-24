# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest

from dockermap.map.container import ContainerMap
from dockermap.map.policy.dep import ContainerDependencyResolver


TEST_MAP_DATA = {
    'a': dict(uses=['b', 'c']),
    'b': dict(uses=['dv', 'f'], links='e.1'),
    'd': dict(uses='e', instances=['1', '2'], attaches='dv'),
    'e': dict(instances=['1', '2']),
    'f': dict(),
    'x': dict(uses=['b', 'f']),
}


class ContainerDependencyTest(unittest.TestCase):
    def setUp(self):
        test_map = ContainerMap('test_map', initial=TEST_MAP_DATA, check_integrity=False)
        self.res = ContainerDependencyResolver(test_map)

    def assertOrder(self, dependency_list, *items):
        iterator = iter(items)
        last_item = iterator.next()
        last_idx = dependency_list.index(last_item)
        for item in iterator:
            index = dependency_list.index(item)
            if index < last_idx:
                self.fail("{0} found before {1}, should be later.".format(item, last_item))

    def test_resolution_order(self):
        a_dep = self.res.get_container_dependencies('test_map', 'a')
        self.assertOrder(a_dep,
                         ('test_map', 'd', None),
                         ('test_map', 'b', None))
        self.assertOrder(a_dep,
                         ('test_map', 'e', None),
                         ('test_map', 'd', None))
        self.assertOrder(a_dep,
                         ('test_map', 'e', '1'),
                         ('test_map', 'b', None))
        self.assertOrder(a_dep,
                         ('test_map', 'f', None),
                         ('test_map', 'b', None))
        x_dep = self.res.get_container_dependencies('test_map', 'x')
        self.assertOrder(x_dep,
                         ('test_map', 'f', None),
                         ('test_map', 'b', None))


if __name__ == '__main__':
    unittest.main()
