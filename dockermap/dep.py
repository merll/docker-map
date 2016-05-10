# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta
from collections import defaultdict
from six import iteritems, with_metaclass


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


class CircularDependency(Exception):
    """
    Indicates that dependencies cannot be resolved, since items are interdependent.
    """
    pass


class BaseDependencyResolver(with_metaclass(ABCMeta, object)):
    """
    Base class for resolving dependencies of hierarchical nodes. Not each node has to be relevant, and on each level
    parent dependencies can be merged with the current node.

    :param initial: Optional: Iterable or dictionary in the format `(dependent_item, dependence)`.
    :type initial: iterable
    """
    def __init__(self, initial=None):
        self._deps = _dependency_dict(initial)

    def __contains__(self, item):
        return item in self._deps

    def merge_dependency(self, item, resolve_parent, parent):
        """
        Called by :meth:`~BaseDependencyResolver.get_dependencies` once on each node. The result is cached for
        re-occurring checks. This method determines the relevancy (and potentially additional dependencies) of the
        current node `item`, and how the result is merged with dependencies from the deeper hierarchy. The latter are
        resolved by calling `resolve_parent(parent)`.

        By default, this function will always return `False`, as the node relevancy is not defined.

        This function should, if applicable, also check for potential infinite recursions and in that case raise
        a :class:`~CircularDependency` exception.

        :param item: Current node.
        :param resolve_parent: Function to check on dependencies deeper in the hierarchy.
        :type resolve_parent: function
        :param parent: Parent node(s).
        :return: Result of the dependency merge. May be boolean, a set, or anything else that represents all
         dependencies.
        :rtype: bool
        """
        return parent is not None and resolve_parent(parent)

    def get_dependencies(self, item):
        """
        Performs a dependency check on the given item.

        :param item: Node to start the dependency check with.
        :return: The result on merged dependencies down the hierarchy.
        """
        def _get_sub_dependency(sub_item):
            e = self._deps.get(sub_item)
            if e is None:
                return ()

            if e.dependencies is NotInitialized:
                e.dependencies = self.merge_dependency(sub_item, _get_sub_dependency, e.parent)
            return e.dependencies

        return _get_sub_dependency(item)

    def get(self, item, default=()):
        """
        Returns the direct dependencies or dependents of a single item. Does not follow the entire dependency path.

        :param item: Node to return dependencies for.
        :param default: Default value to return in case the item is not stored.
        :return: Immediate dependencies or dependents.
        """
        e = self._deps.get(item)
        if e is None:
            return default
        return e.parent

    def reset(self):
        """
        Resets all cached nodes.
        """
        for value in self._deps.values():
            value.dependencies = NotInitialized

    def update(self, items):
        """
        Updates the dependencies with the given items. Note that this may not reset all previously-evaluated and cached
        nodes.

        :param items: Iterable or dictionary in the format `(dependent_item, dependence)`.
        :type items: iterable
        """
        self._deps.update(_dependency_dict(items))


class SingleDependencyResolver(with_metaclass(ABCMeta, BaseDependencyResolver)):
    """
    Abstract, partial implementation of a dependency resolver for nodes in a 1:n relationship, i.e. that each node
    depends on exactly one item.
    """
    def update_backward(self, items):
        """
        Updates the dependencies in the inverse relationship format, i.e. from an iterable or dict that is structured
        as `(item, dependent_items)`. Note that this implementation is only valid for 1:1 relationships, i.e. that each
        node has also exactly one dependent. For other cases, :class:`~MultiDependencyResolver` should be used.

        :param items: Iterable or dictionary in the format `(item, dependent_items)`.
        :type items: iterable
        """
        for parent, sub_items in items:
            for si in sub_items:
                self._deps[si] = CachedDependency(parent)


class MultiDependencyResolver(with_metaclass(ABCMeta, BaseDependencyResolver)):
    """
    Abstract, partial implementation of a dependency resolver for nodes in a m:n relationship, i.e. that each node
    depends on one or multiple items.
    """
    def __init__(self, initial=None):
        self._deps = defaultdict(lambda: CachedDependency(set()), _dependency_dict(initial))

    def merge_dependency(self, item, resolve_parent, parents):
        """
        Performs the same operation as :meth:`~BaseDependencyResolver.merge_dependency`, but considering that the node
        `item` may have multiple dependencies `parent`.

        :param item: Current node.
        :param resolve_parent: Function to check on dependencies deeper in the hierarchy.
        :type resolve_parent: function
        :param parents: Parent nodes.
        :type parents: iterable
        :return: Result of the dependency merge. May be boolean, a set, or anything else that represents all
         dependencies.
        :rtype: bool
        """
        return parents is not None and any(resolve_parent(parent) for parent in parents)

    def update(self, items):
        """
        Updates the dependencies with the given items. Note that this does not reset all previously-evaluated and cached
        nodes.

        :param items: Iterable or dictionary in the format `(dependent_item, dependencies)`.
        :type items: iterable
        """
        for item, parents in _iterate_dependencies(items):
            dep = self._deps[item]
            dep.parent.update(parents)

    def update_backward(self, items):
        """
        Updates the dependencies in the inverse relationship format, i.e. from an iterable or dict that is structured
        as `(item, dependent_items)`. The parent element `item` may occur multiple times.

        :param items: Iterable or dictionary in the format `(item, dependent_items)`.
        :type items: iterable
        """
        for parent, sub_items in _iterate_dependencies(items):
            for si in sub_items:
                dep = self._deps[si]
                dep.parent.add(parent)
