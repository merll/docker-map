# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod
import cStringIO
from tempfile import NamedTemporaryFile


class FinalizedError(Exception):
    """
    Exception type for indicating that a modification operation has been attempted on a :class:`~DockerBuffer` object,
    that had already been finalized earlier.
    """
    pass


class DockerBuffer(object):
    """
    Abstract class for managing Docker file-like objects. Subclasses must override at least :attr:`init_fileobj` with
    a callable which constructs the actual file-like object.

    :param args: Args to :attr:`init_fileobj`.
    :param kwargs: Kwargs to :attr:`init_fileobj`.
    """
    __metaclass__ = ABCMeta

    init_fileobj = None

    def __init__(self, *args, **kwargs):
        if not callable(self.init_fileobj):
            raise ValueError("Class attribute 'init_fileobj' must be callable.")
        self._fileobj = self.init_fileobj(*args, **kwargs)
        self._finalized = False

    def __repr__(self):
        return self._fileobj.getvalue().encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def check_not_finalized(self):
        """
        Checks if the object has been marked as finalized. Should be called once before every write operation.

        :raise FinalizedError: If the object is finalized, and no further changes can be made.
        """
        if self._finalized:
            raise FinalizedError("File cannot be changed after it has been finalized.")

    @property
    def fileobj(self):
        """
        Read-only property, returning the reference to the file-like object.

        :return:
        """
        return self._fileobj

    def getvalue(self):
        """
        Returns the current value of the buffer.

        :return: Representation if the buffer.
        :rtype: unicode
        """
        return self._fileobj.getvalue()

    def finalize(self):
        """
        Marks the buffer as finalized, indicating that no further write operations should be performed. Subclasses
        should perform final operations just before this.
        """
        self._finalized = True

    @abstractmethod
    def save(self, name, encoding=None):
        """
        Saves the buffer content (e.g. to a file). This is abstract since it depends the type of the backing file-like
        object. Implementations will usually finalize the buffer.

        :param name: Name to store the contents under.
        :type name: unicode
        :param encoding: Optional, apply content encoding before saving.
        :type encoding: unicode
        """
        pass

    def close(self):
        """
        Close the file object.
        """
        self._fileobj.close()


class DockerStringBuffer(DockerBuffer):
    """
    Partial implementation of :class:`~DockerBuffer`, backed by a :class:`~cStringIO.StringIO` buffer.
    """
    __metaclass__ = ABCMeta

    init_fileobj = cStringIO.StringIO

    def save(self, name, encoding='utf-8'):
        """
        Save the string buffer to a file. Finalizes prior to saving.

        :param name: File path.
        :type name: unicode
        :param encoding: Optional, default is `utf-8`.
        :type encoding: unicode
        """
        self.finalize()
        with open(name, 'wb+') as f:
            if encoding:
                f.write(self.getvalue().encode(encoding))
            else:
                f.write(self.getvalue())


class DockerTempFile(DockerBuffer):
    """
    Partial implementation of :class:`~DockerBuffer`, backed by a :class:`~tempfile.NamedTemporaryFile`.
    """
    __metaclass__ = ABCMeta

    init_fileobj = lambda self: NamedTemporaryFile('wb+')

    def save(self, name):
        """
        Copy the contents of the temporary file somewhere else. Finalizes prior to saving.

        :param name: File path.
        :type name: unicode
        """
        self.finalize()
        with open(name, 'wb+') as f:
            buf = self._fileobj.read()
            while buf:
                f.write(buf)
                buf = self._fileobj.read()
