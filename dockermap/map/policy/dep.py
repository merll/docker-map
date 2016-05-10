# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import OrderedDict

from six import iteritems

from ...dep import MultiDependencyResolver, CircularDependency


class ContainerDependencyResolver(MultiDependencyResolver):
    """
    Resolves dependencies between :class:`~dockermap.map.config.ContainerConfiguration` instances, based on shared and
    used volumes.
    """
    def merge_dependency(self, item, resolve_parent, parents):
        """
        Merge dependencies of current container with further dependencies; in this instance, it means that first parent
        dependencies are checked, and then immediate dependencies of the current container should be added to the list,
        but without duplicating any entries.

        :param item: Container name.
        :type item: tuple[unicode | str]
        :param resolve_parent: Function to resolve parent dependencies.
        :type resolve_parent: function
        :type parents: iterable
        :return: List of recursively resolved dependencies of this container.
        :rtype: list
        :raise CircularDependency: If the current element depends on one found deeper in the hierarchy.
        """
        def _merge_instances(merge_deps):
            for mm, mc, mi in merge_deps:
                key = mm, mc
                dep_instances = dep.get(key)
                if dep_instances is None:
                    dep[key] = list(mi)
                elif None not in dep_instances:
                    if None in mi:
                        dep[key] = [None]
                    else:
                        new_instances = [ni for ni in mi if ni not in dep_instances]
                        dep_instances.extend(new_instances)

        dep = OrderedDict()
        for p_map, p_config, __ in parents:
            parent_dep = resolve_parent((p_map, p_config))
            if parent_dep:
                _merge_instances(parent_dep)
        _merge_instances(parents)
        if item in dep:
            raise CircularDependency("Circular dependency found for item '{0}'.".format(item))
        return [(d_map, d_config, d_instances)
                for (d_map, d_config), d_instances in iteritems(dep)]
