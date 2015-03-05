# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod

from six import text_type, with_metaclass


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
        return self.__unicode__()

    def __unicode__(self):
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
        :rtype: any
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
        :rtype: any
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
resolve_value = lambda value: value.get() if isinstance(value, lazy_type) else value
