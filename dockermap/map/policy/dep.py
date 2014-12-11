# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..dep import MultiDependencyResolver


class ContainerDependencyResolver(MultiDependencyResolver):
    """
    Resolves dependencies between :class:`~dockermap.map.config.ContainerConfiguration` instances, based on shared and
    used volumes.

    :param container_map: Optional :class:`~dockermap.map.container.ContainerMap` instance for initialization.
    :type container_map: dockermap.map.container.ContainerMap
    """
    def __init__(self, container_map=None):
        items = container_map.dependency_items if container_map else None
        super(ContainerDependencyResolver, self).__init__(items)

    def merge_dependency(self, item, resolve_parent, parents):
        """
        Merge dependencies of current container with further dependencies; in this instance, it means that first parent
        dependencies are checked, and then immediate dependencies of the current container should be added to the list,
        but without duplicating any entries.

        :param item: Container name.
        :type item: tuple[unicode]
        :param resolve_parent: Function to resolve parent dependencies.
        :type resolve_parent: function
        :type parents: iterable
        :return: List of recursively resolved dependencies of this container.
        :rtype: list
        """
        dep = list(parents)
        for parent in parents:
            parent_dep = resolve_parent(parent)
            if parent_dep:
                dep.extend(set(parent_dep).difference(dep))
        return dep

    def get_container_dependencies(self, map_name, container):
        item = map_name, container, None
        return super(ContainerDependencyResolver, self).get_dependencies(item)

    def update(self, container_map):
        """
        Overrides the `update` function of the superclass to use a :class:`~dockermap.map.container.ContainerMap`
        instance.

        :param container_map: :class:`ContainerMap` instance
        :type container_map: dockermap.map.container.ContainerMap
        """
        super(ContainerDependencyResolver, self).update(container_map.dependency_items)

    def update_backward(self, container_map):
        """
        Overrides the `update_backward` function of the superclass to use a
        :class:`~dockermap.map.container.ContainerMap` instance.

        :param container_map: :class:`~dockermap.map.container.ContainerMap` instance
        :type container_map: dockermap.map.container.ContainerMap
        """
        super(ContainerDependencyResolver, self).update_backward(container_map.dependency_items)
