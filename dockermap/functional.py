# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod

from six import iteritems, text_type, with_metaclass, python_2_unicode_compatible


@python_2_unicode_compatible
class AbstractLazyObject(with_metaclass(ABCMeta, object)):
    """
    Abstract superclass class for lazily-resolved values. Runs function ``func`` with ``*args`` and ``**kwargs``, when
    called or the ``get`` function is used. The following also trigger an evaluation:

    * String representation.
    * Equality or inequality check.
    * Contains operator.
    * Iteration.
    * Reduce (pickling).

    :param func: Callable to evaluate.
    :type func: callable
    :param args: Arguments to pass to ``func``.
    :param kwargs: Keyword arguments to pass to ``func``.
    """
    def __init__(self, func, *args, **kwargs):
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def __call__(self):
        return self.get()

    def __str__(self):
        return text_type(self.get())

    def __eq__(self, other):
        return self.get() == other

    def __ne__(self, other):
        return self.get() != other

    def __contains__(self, item):
        return item in self.get()

    def __iter__(self):
        return self.get().__iter__()

    def __reduce__(self):
        return self.__class__, self._func, dict(_args=self._args, _kwargs=self._kwargs)

    @abstractmethod
    def get(self):
        pass

    @property
    def func(self):
        """
        Callable to run for evaluation.

        :return: Callable.
        :rtype: callable
        """
        return self._func

    @property
    def args(self):
        """
        Positional arguments for ``func``.

        :return: Positional arguments.
        :rtype: tuple
        """
        return self._args

    @property
    def kwargs(self):
        """
        Keyword arguments for ``func``.

        :return: Keyword arguments.
        :rtype: dict
        """
        return self._kwargs

    @property
    def value(self):
        """
        Resolved and and returns the value.

        :return: The actual value, resolved by the object.
        """
        return self.get()


class SimpleLazyObject(AbstractLazyObject):
    """
    Simple lazy-resolving object.
    """
    def get(self):
        """
        Resolves and returns the object value.

        :return: The result of evaluating the object.
        """
        return self._func(*self._args, **self._kwargs)


class LazyOnceObject(AbstractLazyObject):
    """
    Like :class:`SimpleLazyObject`, but runs the evaluation only once. Note that even ``None`` will be re-used as a
    valid result.

    :param func: Callable to evaluate.
    :type func: callable
    :param args: Arguments to pass to ``func``.
    :param kwargs: Keyword arguments to pass to ``func``.
    """
    def __init__(self, func, *args, **kwargs):
        super(LazyOnceObject, self).__init__(func, *args, **kwargs)
        self._evaluated = False
        self._val = None

    def get(self):
        """
        Resolves and returns the object value. Re-uses an existing previous evaluation, if applicable.

        :return: The result of evaluating the object.
        """
        if not self._evaluated:
            self._val = self._func(*self._args, **self._kwargs)
            self._evaluated = True
        return self._val

    def __reduce__(self):
        red = super(LazyOnceObject, self).__reduce__()
        red[2].update(_val=self._val, _evaluated=self._evaluated)
        return red

    @property
    def evaluated(self):
        """
        Indicates whether the object has been evaluated before.

        :return: Returns ``True`` in case the object has been evaluated, ``False`` otherwise.
        """
        return self._evaluated


lazy_type = AbstractLazyObject
lazy = SimpleLazyObject
lazy_once = LazyOnceObject

type_registry = {}


def expand_type_name(type_):
    """
    Returns concatenated module and name of a type for identification.

    :param type_: Type:
    :type type_: type
    :return: Type name, as ``<type's module name>.<type name>``.
    :rtype: unicode | str
    """
    return '{0.__module__}.{0.__name__}'.format(type_)


def resolve_value(value):
    """
    Returns the actual value for the given object, if it is a late-resolving object type.
    If not, the value itself is simply returned.

    :param value: Lazy object, registered type in :attr:`type_registry`, or a simple value. In the
     latter case, the value is returned as-is.
    :type value: str | unicode | int | AbstractLazyObject | unknown
    :return: Resolved value.
    """
    if isinstance(value, lazy_type):
        return value.get()
    elif type_registry:
        resolve_func = type_registry.get(expand_type_name(type(value)))
        if resolve_func:
            return resolve_func(value)
    return value


def resolve_deep(values, max_depth=5, types=None):
    """
    Resolves all late-resolving types into their current values to a certain depth in a dictionary or list.

    :param values: Values to resolve of any type.
    :param max_depth: Maximum depth to recurse into nested lists, tuples and dictionaries. Below that depth values are
     returned as they are.
    :type max_depth: int
    :param: Dictionary of types and functions to resolve, that are not registered in ``type_registry``.
    :type: dict[unicode | str, function]
    :return: Resolved values.
    """
    def _resolve_single(value):
        if isinstance(value, lazy_type):
            return value.get()
        elif all_types:
            resolve_func = all_types.get(expand_type_name(type(value)))
            if resolve_func:
                return resolve_func(value)
        return value

    def _resolve_sub(v, level):
        l1 = level + 1
        res_val = _resolve_single(v)
        if l1 < max_depth:
            if isinstance(res_val, (list, tuple)):
                return [_resolve_sub(item, l1) for item in res_val]
            elif isinstance(res_val, dict):
                return {_resolve_single(rk): _resolve_sub(rv, l1) for rk, rv in iteritems(res_val)}
        return res_val

    if types:
        all_types = type_registry.copy()
        all_types.update(types)
    else:
        all_types = type_registry
    return _resolve_sub(values, -1)


def register_type(resolve_type, resolve_func):
    """
    Registers a type for lazy value resolution. Instances of AbstractLazyObject do not have to
    be registered. The exact type must be provided in ``resolve_type``, not a superclass of it.
    Types registered will be passed through the given function by :func:`resolve_value`.

    :param resolve_type: Type to consider during late value resolution.
    :type resolve_type: type
    :param resolve_func: Function to run for retrieving the original value. It needs to accept
     exactly one argument - the substitute value to resolve to the actual value.
    :type resolve_func: function
    """
    if not isinstance(resolve_type, type):
        raise ValueError("Expected type, got {0}.".format(type(resolve_type).__name__))
    if not callable(resolve_func):
        raise ValueError("Function is not callable.")
    type_registry[expand_type_name(resolve_type)] = resolve_func


def uses_type_registry(value):
    """
    Utility function to check whether a certain value would be handled by late value resolution.
    This does not check lazy objects, but only explicitly registered types.

    :param value: Value to check.
    :return: Whether the type of the given value is registered.
    :rtype: bool
    """
    type_name = expand_type_name(type(value))
    return type_name in type_registry
