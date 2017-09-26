# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod
from collections import defaultdict
from six import iteritems, with_metaclass, python_2_unicode_compatible, text_type

from .utils import merge_list


class NotInitialized(object):
    """
    Utility class to locate nodes in the dependency tree where there is no cached dependency structure yet.
    """
    pass


class CachedDependency(object):
    """
    Caching dependencies along the hierarchy.
    """
    __slots__ = ['_parent', '_dependencies']

    def __init__(self, parent, dependencies=NotInitialized):
        self._parent = parent
        self._dependencies = dependencies

    def __repr__(self):
        d = self._dependencies if self._dependencies is not NotInitialized else '<NotInitialized>'
        return 'CachedDependency(parent={0!r}, dependencies={1!r})'.format(self._parent, d)

    @property
    def parent(self):
        """
        Parent node(s).
        """
        return self._parent

    @parent.setter
    def parent(self, value):
        self._parent = value

    @property
    def dependencies(self):
        """
        Boolean, list, or other representation of cached dependencies from the parent. Returns ``NotInitialized`` if
        not cached yet.
        """
        return self._dependencies

    @dependencies.setter
    def dependencies(self, value):
        self._dependencies = value


def _iterate_dependencies(items):
    if not items:
        return ()
    if isinstance(items, dict):
        return iteritems(items)
    return items


def _dependency_dict(items):
    return {item: CachedDependency(parent) for item, parent in _iterate_dependencies(items)}


@python_2_unicode_compatible
class CircularDependency(Exception):
    """
    Indicates that dependencies cannot be resolved, since items are interdependent.
    """
    def __init__(self, item, is_direct=False, *args, **kwargs):
        self._item = item
        self._is_direct = is_direct
        super(CircularDependency, self).__init__(*args, **kwargs)

    def __str__(self):
        if self._is_direct:
            return "{0} refers to itself as a dependency.".format(self._item)
        return "{0} has a dependency that refers back to it.".format(self._item)

    @property
    def item(self):
        return self._item

    @property
    def is_direct(self):
        return self._is_direct


class BaseDependencyResolver(with_metaclass(ABCMeta, object)):
    """
    Base class for resolving dependencies of hierarchical nodes. Not each node has to be relevant, and on each level
    parent dependencies can be merged with the current node.
    """
    def __contains__(self, item):
        return item in self._deps

    def get_default(self):
        """
        Defines a return value if an item is not found on the dependency map or does not have any dependencies.

        :return: Default value.
        """
        return []

    def get_dependencies(self, item):
        """
        Performs a dependency check on the given item.

        :param item: Node to start the dependency check with.
        :return: The result on merged dependencies down the hierarchy.
        """
        def _get_sub_dependency(sub_item):
            e = self._deps.get(sub_item)
            if e is None:
                return self.get_default()

            if e.dependencies is NotInitialized:
                e.dependencies = self.merge_dependency(sub_item, _get_sub_dependency, e.parent)
            return e.dependencies

        return _get_sub_dependency(item)

    def get(self, item):
        """
        Returns the direct dependencies or dependents of a single item. Does not follow the entire dependency path.

        :param item: Node to return dependencies for.
        :return: Immediate dependencies or dependents.
        """
        e = self._deps.get(item)
        if e is None:
            return self.get_default()
        return e.parent

    def reset(self):
        """
        Resets all cached nodes.
        """
        for value in self._deps.values():
            value.dependencies = NotInitialized

    @abstractmethod
    def merge_dependency(self, item, resolve_parent, parent):
        pass

    @abstractmethod
    def update(self, items):
        pass


class ImageDependentsResolver(BaseDependencyResolver):
    def __init__(self, initial=None):
        self._deps = defaultdict(lambda: CachedDependency([]))
        self.update(initial)

    def merge_dependency(self, item, resolve_parent, parents):
        """
        Merge dependencies of element with further dependencies. First parent dependencies are checked, and then
        immediate dependencies of the current element should be added to the list, but without duplicating any entries.

        :param item: Item.
        :param resolve_parent: Function to resolve parent dependencies.
        :type resolve_parent: function
        :type parents: collections.Iterable
        :return: List of recursively resolved dependencies of this container.
        :rtype: list
        :raise CircularDependency: If the current element depends on one found deeper in the hierarchy.
        """
        dep = []
        for parent_key in parents:
            if item == parent_key:
                raise CircularDependency(item, True)
            parent_dep = resolve_parent(parent_key)
            if item in parent_dep:
                raise CircularDependency(item)
            merge_list(dep, parent_dep)
        merge_list(dep, parents)
        return dep

    def update(self, items):
        """
        Updates the dependencies in the inverse relationship format, i.e. from an iterable or dict that is structured
        as `(item, dependent_items)`. Note that this implementation is only valid for 1:1 relationships, i.e. that each
        node has also exactly one dependent. For other cases, :class:`~MultiDependencyResolver` should be used.

        :param items: Iterable or dictionary in the format `(item, dependent_items)`.
        :type items: collections.Iterable
        """
        for parent, sub_item in _iterate_dependencies(items):
            dep = self._deps[sub_item]
            if parent not in dep.parent:
                dep.parent.append(parent)


class MultiForwardDependencyResolver(with_metaclass(ABCMeta, BaseDependencyResolver)):
    """
    Abstract, partial implementation of a dependency resolver for nodes in a m:n relationship, i.e. that each node
    depends on one or multiple items.
    """
    def __init__(self, initial=None):
        self._deps = defaultdict(lambda: CachedDependency([]), _dependency_dict(initial))

    def update(self, items):
        """
        Updates the dependencies with the given items. Note that this does not reset all previously-evaluated and cached
        nodes.

        :param items: Iterable or dictionary in the format `(dependent_item, dependencies)`.
        :type items: collections.Iterable
        """
        for item, parents in _iterate_dependencies(items):
            dep = self._deps[item]
            merge_list(dep.parent, parents)


class MultiReverseDependencyResolver(with_metaclass(ABCMeta, BaseDependencyResolver)):
    def __init__(self, initial=None):
        self._deps = defaultdict(lambda: CachedDependency([]))
        self.update(initial)

    def update(self, items):
        """
        Updates the dependencies in the inverse relationship format, i.e. from an iterable or dict that is structured
        as `(item, dependent_items)`. The parent element `item` may occur multiple times.

        :param items: Iterable or dictionary in the format `(item, dependent_items)`.
        :type items: collections.Iterable
        """
        for parent, sub_items in _iterate_dependencies(items):
            for si in sub_items:
                dep = self._deps[si]
                if parent not in dep.parent:
                    dep.parent.append(parent)
