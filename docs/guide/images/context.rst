.. _build_context:

Working with the DockerContext
==============================
The context is a tar file, that is submitted to the API in order to define the image building process. It has to
include the Dockerfile and all necessary other files. The latter are all files referenced to in any ``ADD`` command.
For syntax of ``ADD`` is::

    ADD <source> <destination>

where ``source`` in this case refers to the path inside the build context, i.e. the tar file root.

When you add files to a :class:`~dockermap.build.dockerfile.DockerFile` using
:meth:`~dockermap.build.dockerfile.DockerFile.add_file` and :meth:`~dockermap.build.dockerfile.DockerFile.add_archive`,
it generates a list of used files and directories. These can be automatically added to a
:class:`~dockermap.build.context.DockerContext`. For most common build scenarios, you may start the build process
directly by calling :meth:`~dockermap.map.base.DockerClientWrapper.build`, e.g.::

    client.build_from_file(dockerfile, 'new_base_image', add_latest_tag=True, rm=True)

This automatically generates the context and uploads it. However, the context can also be modified further beforehand.

Creating a DockerContext
------------------------
For generating a :class:`~dockermap.build.context.DockerContext` explicitly
from an existing :class:`~dockermap.build.dockerfile.DockerFile`, just pass it to the constructor::

    with DockerContext(dockerfile) as context:
        ...

This will create a new compressed tar archive, add the generated Dockerfile (string buffer) and the referenced
files. Note that the :class:`~dockermap.build.dockerfile.DockerFile` fill be finalized and cannot be modified further
after this.

The ``with`` (Python context manager syntax) should be used, since :class:`~dockermap.build.context.DockerContext`
generates a temporary file which is automatically removed at the end of the block.

It is also possible to pass in a path to a file, e.g.::

    with DockerContext(path_to_dockerfile) as context:
        ...

In that case, referenced files are not added automatically and have to be placed using the following methods.

Adding more files
-----------------
:class:`~dockermap.build.context.DockerContext` provides the methods :meth:`~dockermap.build.context.DockerContext.add`
and :meth:`~dockermap.build.context.DockerContext.addfile`, which refer to
:meth:`tarfile.TarFile.add` and :meth:`tarfile.TarFile.addfile`. Besides that,
:meth:`~dockermap.build.context.DockerContext.addarchive` copies the contents of another tar archive, including the
structure of files and directories.

For using :meth:`~dockermap.build.context.DockerContext.addfile`, a :class:`tarfile.TarInfo` object is required. You can
obtain that using :meth:`~dockermap.build.context.DockerContext.gettarinfo`, which calls
:meth:`tarfile.TarFile.gettarinfo`.

Using the context
-----------------
Before sending the file to the Docker Remote API, the underlying tar archive has to be closed. This is handled by
:meth:`~dockermap.build.context.DockerContext.finalize`. Note that the underlying tar archive is closed from that point
and can no longer be modified.

The context tarball is transferred to Docker with
:meth:`~dockermap.map.base.DockerClientWrapper.build_from_context`::

    client = DockerClientWrapper('unix://var/run/docker.sock')
    with DockerContext(path_to_dockerfile) as context:
        ...
        context.finalize()
        client.build_from_context(context, 'new_image')

In fact, :meth:`dockermap.map.base.DockerClientWrapper.build_from_file` is only a convenience wrapper around it. It
finalizes the :class:`~dockermap.build.context.DockerContext` object automatically.

Getting more information
------------------------
Although it may not be relevant in practice, the entire context tarball could be stored to an archive using
:meth:`~dockermap.build.context.DockerContext.save`. By default this is a gzip compressed tar archive, but the actual
method (which also needs to be specified to the Docker Remote API) can be read from the
:attr:`~dockermap.build.context.DockerContext.stream_encoding` attribute:

* ``gzip`` means that the tarball is in the default format, i.e. `.tar.gz`;
* ``bzip2`` indicates a bzip compressed tar archive;
* and ``None`` means that the tar archive is not compressed.

In case you would like to know the name of the temporary underlying tar archive, without making a copy through
:meth:`~dockermap.build.context.DockerContext.save`, the property
:attr:`~dockermap.build.context.DockerContext.name` is available.
