.. _shortcuts:

Shortcuts for Dockerfiles
=========================

A couple of common commands in a `Dockerfile` require writing a lot of repetitive code. In combination with variables
from Python code, additional adaptions (e.g. escaping of strings, reformatting of certain parameters) has to be made.
The :mod:`~dockermap.shortcuts` module includes some utilities -- more precisely string formatters -- for use
in a `Dockerfile`. They are also included in other modules of Docker-Map. Of course the generated commands can also be
applied to any other command line setting, e.g. ``run`` calls in `Fabric`.

Users and groups
----------------
Since Docker does not use the host systems names, you either have to rely on only user ids, or create users and groups
within the image. The former may not always be sufficient. Therefore, it is more pratical to include commands such
as ``RUN adduser username ...``. Additionally, when sharing volumes between images, it is most practical if user and
group ids are consistent between the containers that are accessing them.

The utility :func:`~dockermap.shortcuts.adduser` generates a `adduser` command with the arguments ``username`` and
``uid`` -- other keyword arguments are optional. The optional default values assume that typically, you need a user for
running programs, but not for login. They can be overwritten in any other case:

* ``system``: Create a system user; default is ``False``.
* ``no_login``: Do not allow the user to login and skip creation of a `home` directory; default is ``True``.
* ``no_password``: Do not issue a password for the user. It is set to ``False`` by default, but implied by ``no_login``.
* ``group``: Add a user group for the user. It is set to ``False`` by default. In Dockerfiles, you might want to
  call :func:`~dockermap.shortcuts.addgroupuser` instead for making the id predicable.
* ``gecos``: Optional, but should usually be set to appropriate user information (e.g. full name) when ``no_login`` is
  set to ``False``, as it avoids interactive prompts.

Similarly, :func:`~dockermap.shortcuts.addgroup` creates a `addgroup` command with the arguments ``groupname`` and
``gid``. The optional ``system`` keyword argument decides whether to create a system user.
For adding users to a group, use :func:`~dockermap.shortcuts.assignuser` with the arguments ``username`` and a list of
groups in ``groupnames``.

The three aforementioned functions can be comined easily with :func:`~dockermap.shortcuts.addgroupuser`.  Like the
:func:`~dockermap.shortcuts.adduser` shortcut, it has two mandatory arguments ``username`` and ``uid``, and provides the
keyword arguments ``system``, ``no_login``, ``no_password``, and ``gecos`` with identical defaults. Additionally, a list
of groups can be passed in ``groupnames``. A user and group are created with identical name and id. When needed, the
user is additionally added to a list of additional groups.

For example, for creating a user ``nginx`` for running web server workers with, inlcude the following commands::

    df = DockerFile(...)
    ... #  Additional build commands
    df.run(addgroupuser('nginx', 2000))


If you are sharing files or a socket with an app server container named `apps` and the group id `2001`, the following
code creates that group and assigns the web server user to it::

    df = DockerFile(...)
    ... #  Additional build commands
    df.run_all(
        addgroup('apps', 2001),
        addgroupuser('nginx', 2000, ['apps']),
    )


.. tip::
   The user and group names, as well as their ids, are only written here as literals for illustration purposes. The
   main intention of the :class:`~dockermap.build.dockerfile.DockerFile` implementation is that you do *not* hardcode
   these things, but instead refer to variables.

.. note::
   `adduser` and `addgroup` are specific to Debian-based Linux distributions. Therefore, they will be replaced with
   more system-independent commands in future versions.


User names of most Docker-Map functions are formatted by :func:`~dockermap.shortcuts.get_user_group`. It accepts the
following input, which is returned as a string in the format ``user:group``:

* Tuple: should contain exactly two elements.
* Integer: assumes only a user id, which is identical to the group id, and will be returned as ``uid:gid``.
* Strings: If they include a colon, are returned as is; otherwise formatted as ``name:name``, where `name` is assumed to
  be the user and group id.


Files and directories
---------------------
There are shortcuts available for a few common tasks, which are more infrequently used in Dockerfiles, but otherwise
applied by Docker-Map. Most of them in syntax and functionality correspond with the identical unix shell commands.

The command :func:`~dockermap.shortcuts.mkdir` returns a string for creating directories. By default, parent
directories are created as necessary, which can be deactivated by setting ``create_parent=False``. Additionally,
a bash `if`-clause can be inserted to check first whether the directory already exists. This is not the default, but
set with ``check_if_exists=True``.

Commands generated by utility functions :func:`~dockermap.shortcuts.chmod` modify file system permission flags,
:func:`~dockermap.shortcuts.chown` changes the owner, just like their corresponding unix commands. The `chmod`
permissions can be written in any notation as accepted by the unix command line. The user name for `chown` is expanded
to a ``user:group`` notation using :func:`~dockermap.shortcuts.get_user_group`. For removing files,
:func:`~dockermap.shortcuts.rm` can be used for generating a command line.

By default :func:`~dockermap.shortcuts.chmod`, :func:`~dockermap.shortcuts.chown`, and :func:`~dockermap.shortcuts.rm`
include the ``-R`` argument, i.e. they apply changes recursively. This behavior is changed by passing the optional
keyword argument ``recursive=False``.

A shortcut for combining :func:`~dockermap.shortcuts.chmod`, :func:`~dockermap.shortcuts.chown`, and
:func:`~dockermap.shortcuts.mkdir` is :func:`~dockermap.shortcuts.mkdir_chown`: It generates a concatenated command
for creating a directory ``path`` and applying file system ownership from ``user_group`` and permission flags from
``permissions``. Both are not mandatory and skipped if set to ``None``. The default for ``permissions`` is
``ug=rwX,o=rX``. Note that in this function, :func:`~dockermap.shortcuts.chmod`
and :func:`~dockermap.shortcuts.chown` are not recursive by default, but optional with setting ``recursive=True``.
Optionally, an `if`-clause can check whether the directory exists with the keyword argument ``check_if_exists=True``;
if it does, the other two functions `chmod` and `chown` are nevertheless applied.

For example an empty directory, available only to the user with id `2001`, is prepared with the following command::

    df = DockerFile(...)
    ... #  Additional build commands
    df.run(mkdir_chown('/var/lib/app', 2001, 'u=rwX,go='))


Miscellaneous
-------------
There are two utility functions for downloading files: :func:`~dockermap.shortcuts.curl` and
:func:`~dockermap.shortcuts.wget`. Both have the URL as first argument, and an optional output file as second. Note that
both programs need to be available in the base image, and that they behave differently when not provided with an output
file parameter: `curl` prints the downloaded file to `stdout`, whereas `wget` attempts to detect the file name and
stores it in the current directory.

.. tip:: A `Dockerfile` build can also download files with the ``ADD`` command.

Handling gzip-compressed tar archives (e.g. from downloads in Docker builds) can furthermore be supported with
:func:`~dockermap.shortcuts.targz` and :func:`~dockermap.shortcuts.untargz`. Both have the archive name as the first
argument. For :func:`~dockermap.shortcuts.targz`, specifying source files as second argument is obligatory, whereas
:func:`~dockermap.shortcuts.untargz` has an optional destination argument, but will by default extract to the
current directory.
