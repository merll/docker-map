# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import abstractmethod, ABCMeta
from collections import namedtuple, defaultdict
import six


Dependency = namedtuple('Dependency', ('parent', 'dependency_found'))


def _dependency_dict(items):
    if items is None:
        return {}
    if isinstance(items, dict):
        iterator = six.iteritems(items)
    else:
        iterator = items
    return dict((item, Dependency(parent, None)) for item, parent in iterator)


class CircularDependency(Exception):
    """
    Indicates that dependencies cannot be resolved, since items are interdependent.
    """
    pass


class BaseDependencyResolver(object):
    """
    Base class for resolving dependencies of hierarchical nodes. Not each node has to be relevant, and on each level
    parent dependencies can be merged with the current node.
    In a subclass, at least `merge_dependency` and `check_circular_func` have to be implemented.

    :param initial: Optional: Iterable or dictionary in the format `(dependent_item, dependence)`.
    :type initial: iterable
    """
    __metaclass__ = ABCMeta

    def __init__(self, initial=None):
        self._deps = _dependency_dict(initial)

    def merge_dependency(self, item, resolve_parent, parent):
        """
        Called by `get_dependencies` once on each node. The result is cached for re-occurring checks. This method
        determines the relevancy (and potentially additional dependencies) of the current node `item`, and how the
        result is merged with dependencies from the deeper hierarchy. The latter are resolved by calling
        `resolve_parent(parent)`.
        By default, this function will always return `False`, as the node relevancy is not defined. It should never
        return `None`, only empty lists, strings etc.

        :param item: Current node.
        :type item: any
        :param resolve_parent: Function to check on dependencies deeper in the hierarchy.
        :type resolve_parent: __builtin__.function
        :param parent: Parent node(s).
        :type parent: any
        :return: Result of the dependency merge. May be just boolean, a set, or anything else. Should return `False`
            if there are no dependencies, not `None`.
        :rtype: bool
        """
        return parent is not None and resolve_parent(parent)

    @abstractmethod
    def check_circular_func(self, start_item):
        """
        Function to be implemented by subclasses to check whether nodes are interdependent. Needs to return a function
        that accepts one argument: the current node. That function should return `True` on a circular dependency,
        `False` otherwise.

        :param start_item: Node that the dependency check started with.
        :type start_item: any
        :return: Function that checks if interdependent items have been found.
        :rtype: __builtin__.function
        """
        pass

    def get_dependencies(self, item):
        """
        Performs a dependency check on the given item.

        :param item: Node to start the dependency check with.
        :type item: any
        :return: The result on merged dependencies down the hierarchy.
        :raise CircularDependency: If some element in the hierarchy depends on the start node.
        """
        def _get_sub_dependency(sub_item):
            e = self._deps.get(sub_item)
            if e is not None:
                if e.dependency_found is None:
                    if circular_func(e.parent):
                        raise CircularDependency("Circular dependency found for item '{0}' at '{1}'.".format(item, sub_item))
                    dep_found = self.merge_dependency(sub_item, _get_sub_dependency, e.parent)
                    self._deps[sub_item] = Dependency(e.parent, dep_found)
                    return dep_found
                return e.dependency_found
            return False

        circular_func = self.check_circular_func(item)
        return _get_sub_dependency(item) or ()

    def update(self, items):
        """
        Updates the dependencies with the given items. Note that this may not reset all previously-evaluated and cached
        nodes.

        :param items: Iterable or dictionary in the format `(dependent_item, dependence)`.
        :type items: iterable
        """
        self._deps.update(_dependency_dict(items))


class SingleDependencyResolver(BaseDependencyResolver):
    """
    Abstract, partial implementation of a dependency resolver for nodes in a 1:n relationship, i.e. that each node
    depends on exactly one item.
    """
    __metaclass__ = ABCMeta

    def check_circular_func(self, start_item):
        """
        Provides the check if the dependence equals the node `start_item`, that the check originally started with.

        :type start_item: any
        :return: Function with argument `item` that checks for `item == start_item`.
        :rtype: __builtin__.function
        """
        return lambda item: item == start_item

    def update_backward(self, items):
        """
        Updates the dependencies in the inverse relationship format, i.e. from an iterable or dict that is structured
        as `(item, dependent_items)`.

        :param items: Iterable or dictionary in the format `(item, dependent_items)`.
        :type items: iterable
        """
        for parent, sub_items in items:
            for si in sub_items:
                self._deps[si] = Dependency(parent, None)


class MultiDependencyResolver(BaseDependencyResolver):
    """
    Abstract, partial implementation of a dependency resolver for nodes in a m:n relationship, i.e. that each node
    depends on one or multiple items.
    """
    __metaclass__ = ABCMeta

    def __init__(self, initial=None):
        self._deps = defaultdict(lambda: Dependency(set(), None), _dependency_dict(initial))

    def check_circular_func(self, start_item):
        """
        Provides the check if `start_item` is in any of the dependencies.

        :type start_item: any
        :return: Function with argument `items` that checks for `start_item in items`.
        :rtype: __builtin__.function
        """
        return lambda items: start_item in items

    def merge_dependency(self, item, resolve_parent, parents):
        """
        Performs the same operation as `BaseDependencyResolver.merge_dependency()`, but considering that the node
        `item` may have multiple dependencies `parent`.

        :param item: Current node.
        :type item: any
        :param resolve_parent: Function to check on dependencies deeper in the hierarchy.
        :type resolve_parent: __builtin__.function
        :param parents: Parent nodes.
        :type parents: iterable
        :return: Result of the dependency merge. May be just boolean, a set, or anything else. Should return `False`
            if there are no dependencies, not `None`.
        :rtype: bool
        """
        return parents is not None and any(resolve_parent(parent) for parent in parents)

    def update(self, items):
        """
        Updates the dependencies with the given items. Note that this may not reset all previously-evaluated and cached
        nodes.

        :param items: Iterable or dictionary in the format `(dependent_item, dependencies)`.
        :type items: iterable
        """
        for item, parents in six.iteritems(_dependency_dict(items)):
            dep = self._deps[item]
            self._deps[item] = Dependency(dep.parent.union(parents.parent), None)

    def update_backward(self, items):
        """
        Updates the dependencies in the inverse relationship format, i.e. from an iterable or dict that is structured
        as `(item, dependent_items)`. The parent element `item` may occur multiple times.

        :param items: Iterable or dictionary in the format `(item, dependent_items)`.
        :type items: iterable
        """
        if isinstance(items, dict):
            iterator = six.iteritems(items)
        else:
            iterator = items
        for parent, sub_items in iterator:
            for si in sub_items:
                dep = self._deps[si]
                dep.parent.add(parent)
                self._deps[si] = Dependency(dep.parent, None)
