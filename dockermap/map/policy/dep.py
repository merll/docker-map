# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ...dep import MultiForwardDependencyResolver, MultiReverseDependencyResolver, CircularDependency
from ...utils import merge_list
from ..input import ItemType


class ContainerDependencyMergeMixin(object):
    """
    Resolves dependencies between :class:`~dockermap.map.config.container.ContainerConfiguration` instances, based on
    shared and used volumes.
    """
    def merge_dependency(self, item, resolve_parent, parents):
        """
        Merge dependencies of current configuration with further dependencies; in this instance, it means that in case
        of container configuration first parent dependencies are checked, and then immediate dependencies of the current
        configuration should be added to the list, but without duplicating any entries.

        :param item: Configuration item.
        :type item: (unicode | str, unicode | str, unicode | str, unicode | str)
        :param resolve_parent: Function to resolve parent dependencies.
        :type resolve_parent: function
        :type parents: collections.Iterable[(unicode | str, unicode | str, unicode | str, unicode | str)]
        :return: List of recursively resolved dependencies of this container.
        :rtype: list[(unicode | str, unicode | str, unicode | str, unicode | str)]
        :raise CircularDependency: If the current element depends on one found deeper in the hierarchy.
        """
        dep = []
        for parent_key in parents:
            if item == parent_key:
                raise CircularDependency(item, True)
            if parent_key.config_type == ItemType.CONTAINER:
                parent_dep = resolve_parent(parent_key)
                if item in parent_dep:
                    raise CircularDependency(item)
                merge_list(dep, parent_dep)
        merge_list(dep, parents)
        return dep


class ContainerDependencyResolver(ContainerDependencyMergeMixin, MultiForwardDependencyResolver):
    pass


class ContainerDependentsResolver(ContainerDependencyMergeMixin, MultiReverseDependencyResolver):
    pass
