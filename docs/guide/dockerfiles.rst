.. _build_images:

Building images with DockerFile
===============================
The functionality of :class:`~dockermap.build.dockerfile.DockerFile` is centered around creating `Dockerfile`'s for
Docker images. Although it is not particularly hard to write them directly, doing so requires you to remember what to
configure where. In some instances (e.g. commands, ports etc.) this may be done at run-time using a configuration
utility. However, if there are more dynamic elements, e.g. paths and version numbers, you can end up having to change
them in multiple places.

This implementation aims to make Dockerfiles easy to generate by Python code. Approaches in detail may vary, i.e. some
may prefer to insert commands one-by-one, whereas others would rather use a format string to insert variables. It is
possible to combine such methods.

Basic instantiation
-------------------
A new `Dockerfile` can be created with the following commands::

    df = DockerFile('ubuntu', maintainer='ME, me@example.com', initial='RUN apt-get update\nRUN apt-get -y upgrade')


The first argument is the base image, as every new Docker image should have one.
The ``maintainer`` argument is optional, and is written with a ``MAINTAINER`` prefix. Afterwards, the contents of
``initial`` (also optional) are written to the Dockerfile.

Internally, instantiation creates a string buffer and some configuration variables. All action commands where the order
is relevant, e.g. ``RUN``, are written to this buffer immediately, whereas configuration commands such as ``EXPOSE`` are
delayed until a finalization step.

Except for being embedded in a context tarball, the Dockerfile is never actually stored by itself. If you wish to do so,
you can use :func:`~dockermap.build.dockerfile.DockerFile.save`.


Action commands
===============
The following actions are performed on the string buffer immediately:

Initial contents
----------------
Passing in a base image, a maintainer, or ``initial`` contents on instantiation. Plain Dockerfile commands can be used
in ``initial``, as found in the `Dockerfile reference`_. The base image is prefixed with ``FROM``, whereas the
maintainer is inserted with ``MAINTAINER``. None of the ``initial`` commands are processed any further, so they should
be formatted properly and contain line breaks.

Run commands
------------
In order to insert ``RUN`` commands for execution during the build process, use
:func:`~dockermap.build.dockerfile.DockerFile.run` and
:func:`~dockermap.build.dockerfile.DockerFile.run_all`. They are convenience methods for ``prefix('RUN', 'command')``
and ``prefix_all('RUN', 'command 1', 'command 2', ...)``.

Adding files
------------
Files can be added using :func:`~dockermap.build.dockerfile.DockerFile.add_file` and
:func:`~dockermap.build.dockerfile.DockerFile.add_archive`. The former adds a single file or directory, whereas the
latter adds the contents of an tar archive. By default, all files and directories will be inserted at the root of
the container's filesystem, maintaining their original structure of subdirectories where applicable.

Inserting a file or archive also adds an entry to a list which is used for building the `context <build_context>`
tarball. The latter carries all file-based information that is later sent to the Docker Remote API, including the
finalized `Dockerfile`. Files and directories will simply be added to the context archive, whereas archives' contents
are extracted and recompressed without storing additional temporary files.

Target directories inside the image can be specified for :func:`~dockermap.build.dockerfile.DockerFile.add_file` using
further arguments. For archives, this is currently not supported, so existing tarballs should be structured in a
way suitable for the image.

For example, a file may also be added with the following arguments::

    dockerfile.add_file('~/my_file', '/new_dir/my_file', '/another_file', expanduser=True, remove_final=True)


**Explanation:**

* The first argument is the current actual place in the file system from where Docker-Map is run. If this includes
  variables, such as the current user home ``~``, ``expanduser`` should be set to ``True`` for resolving it to an
  absolute path name. Similarly, environment variables can be used when passing ``expandvars=True``.
* The second argument defines the target path in the final image. By default, the file would have ended up in
  ``/my_file``.
* The third argument is also optional, and specifies the path inside the context archive. By default it is identical
  to the image's destination path, and can be used in case conflicts arise from adding multiple files or directories
  with identical names.
* ``remove_final`` inserts a removal command (e.g. `RUN rm -R /new_dir/my_file`) at the end of the Dockerfile, but
  before configuration commands. You may want to set this to clean up the file system of the final image from files and
  directories that were only needed during the build process. Please note that due to the file system layering that
  Docker uses, this will not actually make the image smaller.

Comments and blank lines
------------------------
Comments can be inserted with :func:`~dockermap.build.dockerfile.DockerFile.comment`, which is only a convenience for
``prefix('#', 'comment')``. Passing ``None`` inserts an empty comment line. Blank lines are inserted with
:func:`~dockermap.build.dockerfile.DockerFile.blank`. Note that these only have an effect if you actually store the
Dockerfile somewhere.

Miscellaneous Docker commands
-----------------------------
Any Dockerfile command, or a series thereof, can be inserted with :func:`~dockermap.build.dockerfile.DockerFile.prefix`
and :func:`~dockermap.build.dockerfile.DockerFile.prefix_all`.
These insert strings prefixed with a Dockerfile command. Following convenience methods should be preferred where
available.

Direct write access
-------------------
Strings with Dockerfile contents may also be written directly using :func:`~dockermap.build.dockerfile.DockerFile.write`
and :func:`~dockermap.build.dockerfile.DockerFile.writeline` (same, but appends a line break) and
:func:`~dockermap.build.dockerfile.DockerFile.writelines` (for multiple). They are not further processed besides that.


Configuration commands
======================
The following are set as properties to a Dockerfile. They are appended as soon as
:func:`~dockermap.build.dockerfile.DockerFile.finalize` is called. Afterwards no more changes are allowed to the
object. Typically it is not necessary to call :func:`~dockermap.build.dockerfile.DockerFile.finalize` manually.

Volumes
-------
Setting :attr:`~dockermap.build.dockerfile.DockerFile.volumes` defines the list of volumes that a container in its
default configuration will share. The list will be inserted prefixed with a ``VOLUME`` command, before any other of the
following finalizing commands.

Entry point and default command
-------------------------------
:attr:`~dockermap.build.dockerfile.DockerFile.entrypoint` and
:attr:`~dockermap.build.dockerfile.DockerFile.command` do the same as inserting ``ENTRYPOINT`` and ``CMD`` in the
Dockerfile. They can be set either as a list/tuple of strings, or a single string separated with spaces. Depending on
:attr:`~dockermap.build.dockerfile.DockerFile.command_shell`, they are either written as a shell command in the
Dockerfile (i.e. with spaces) or as an exec command (i.e. as a list).

The :attr:`~dockermap.build.dockerfile.DockerFile.command_user` property sets the default user for ``COMMAND`` and
``ENTRYPOINT``. It is therefore inserted directly before them.
In contrast to inserting the ``USER`` command directly, this does not change the user for other
commands in the Dockerfile. You can still use ``prefix('USER', 'username')`` if you need to change users during the
build process.

Exposed ports
-------------
:attr:`~dockermap.build.dockerfile.DockerFile.expose` can be set as a single string, integer, or as a list or tuple
thereof. It will be written to the Dockerfile with the ``EXPOSE`` command; if applicable, multiple ports are separated
with spaces.


Building the Docker image
=========================
For starting the build process, pass the :class:`~dockermap.build.dockerfile.DockerFile` to the Docker Remote API with
the enhanced client function :func:`~dockermap.map.base.DockerClientWrapper.build_from_file`::

    client = DockerClientWrapper('unix://var/run/docker.sock')
    dockerfile = DockerFile('ubuntu', maintainer='ME, me@example.com')
    dockerfile.add_file(...)
    dockerfile.run_all(...)
    ...
    client.build_from_file(dockerfile, 'new_image')

.. _Dockerfile reference: http://docs.docker.com/reference/builder/
