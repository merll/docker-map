# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import tarfile

from .buffer import DockerTempFile
from .dockerfile import DockerFile


class DockerContext(DockerTempFile):
    """
    Class for constructing a Docker context tarball, that can be sent to the remote API. If a :class:`~DockerFile`
    instance is added, the resulting Dockerfile and files added there are considered automatically.

    :param dockerfile: Optional :class:`~DockerFile` instance, or file path to a Dockerfile.
    :type dockerfile: DockerFile or unicode
    :param compression: Compression for the tarball; default is gzip (`gz`); use `bz2` for bzip2.
    :type compression: unicode
    :param encoding: Encoding for the tarfile; default is `utf-8`.
    :type encoding: unicode
    :param finalize: Finalize the tarball immediately.
    :type finalize: bool
    :param kwargs: Additional kwargs for :func:`tarfile.open`.
    """
    def __init__(self, dockerfile=None, compression='gz', encoding='utf-8', finalize=False, **kwargs):
        super(DockerContext, self).__init__()
        open_mode = ':'.join(('w', compression or ''))
        if compression == 'gz':
            self._stream_encoding = 'gzip'
        elif compression == 'bz2':
            self._stream_encoding = 'bzip2'
        else:
            self._stream_encoding = None
        self.tarfile = tarfile.open(mode=open_mode, fileobj=self._fileobj, encoding=encoding, **kwargs)
        if dockerfile is not None:
            self.add_dockerfile(dockerfile)
        if finalize:
            if dockerfile is None:
                raise ValueError("Cannot finalize the docker context tarball without a dockerfile object.")
            self.finalize()

    def add(self, name, *args, **kwargs):
        """
        Add a file or directory to the context tarball.

        :param name: File or directory path.
        :type name: unicode
        :param args: Additional args for :meth:`tarfile.TarFile.add`.
        :param kwargs: Additional kwargs for :meth:`tarfile.TarFile.add`.
        """
        self.tarfile.add(name, *args, **kwargs)

    def addfile(self, *args, **kwargs):
        """
        Add a file to the tarball using a :class:`~tarfile.TarInfo` object. For details, see
        :meth:`tarfile.TarFile.addfile`.

        :param args: Args to :meth:`tarfile.TarFile.addfile`.
        :param kwargs: Kwargs to :meth:`tarfile.TarFile.addfile`
        """
        self.tarfile.addfile(*args, **kwargs)

    def addarchive(self, name):
        """
        Add (i.e. copy) the contents of another tarball to this one.

        :param name: File path to the tar archive.
        :type name: unicode
        """
        with tarfile.open(name, 'r') as st:
            for member in st.getmembers():
                self.tarfile.addfile(member, st.extractfile(member.name))

    def add_dockerfile(self, dockerfile):
        """
        Add a Dockerfile to the context. If it is a :class:`DockerFile` instance, files and archive contents added there
        will automatically be copied to the tarball. The :class:`DockerFile` will be finalized.

        :param dockerfile: :class:`DockerFile` instance or file path to a Dockerfile.
        :type dockerfile: DockerFile or unicode
        """
        if isinstance(dockerfile, DockerFile):
            dockerfile.finalize()
            dockerfile_obj = dockerfile.fileobj
            for path, arcname in dockerfile._files:
                self.add(path, arcname=arcname)
            for archive in dockerfile._archives:
                self.addarchive(archive)
            tarinfo = tarfile.TarInfo('Dockerfile')
            tarinfo.size = dockerfile_obj.tell()
            dockerfile_obj.seek(0)
            self.tarfile.addfile(tarinfo, dockerfile_obj)
        else:
            self.add(dockerfile, arcname='Dockerfile')

    def gettarinfo(self, *args, **kwargs):
        """
        Returns a :class:`~tarfile.TarInfo` object. See :meth:`tarfile.TarFile.gettarinfo`.

        :param args: Args to :meth:`tarfile.TarFile.gettarinfo`.
        :param kwargs: Kwargs to :meth:`tarfile.TarFile.gettarinfo`.
        :return: :class:`~tarfile.TarInfo` object.
        :rtype: tarfile.TarInfo
        """
        return self.tarfile.gettarinfo(*args, **kwargs)

    def finalize(self):
        """
        Finalizes the context tarball and sets the file position to 0. The tar file is then closed, but the underlying
        file object can still be read.
        """
        self.tarfile.close()
        self._fileobj.seek(0)

    @property
    def name(self):
        """
        Returns the name of the underlying file object.

        :return: Name of the file object.
        :rtype: unicode
        """
        return self._fileobj.name

    @property
    def stream_encoding(self):
        """
        Returns the stream encoding, as used when calling :meth:`docker.client.Client.build`.

        :return: Stream encoding.
        :rtype: unicode
        """
        return self._stream_encoding

    def save(self, name):
        """
        Saves the entire Docker context tarball to a separate file.

        :param name: File path to save the tarball into.
        :type name: unicode
        """
        with open(name, 'wb+') as f:
            while True:
                buf = self._fileobj.read()
                if not buf:
                    break
                f.write(buf)
