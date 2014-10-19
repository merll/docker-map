.. _shortcuts:

Utilitities for image building
==============================

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
   more system-independent commands in future versions. Where possible, this will be done without affecting the minimal
   functionality commonly required in Dockerfiles (i.e. creating users and groups separately, no login, no home
   directory etc.).


User names of most Docker-Map functions are formatted by :func:`~dockermap.shortcuts.get_user_group`. It accepts the
following input, which is returned as a string in the format ``user:group``:

* Tuple: should contain exactly two elements.
* Integer: assumes only a user id, which is identical to the group id, and will be returned as ``uid:gid``.
* Strings: If they include a colon, are returned as is; otherwise formatted as ``name:name``, where `name` is assumed to
  be the user and group id.


Files and directories
---------------------


Miscellaneous
-------------
