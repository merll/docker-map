.. _container_maps:

Managing containers
===================
Several practices have evolved around what should be part of a single image or separate. It is mainly a trade-off
between simplicity and flexibility: On one hand, if one container instance encloses all necessary programs, it is easier
to connect those, as they share one common file system and network. Beside security concerns, this can turn out to be
impractical on the other hand. A single image has to be maintained and updated in this form, which can become
complex as well and takes more time to build. In larger system landscapes monolithic images also create redundancy of
systems that could otherwise be shared easily, e.g. databases. Separate containers for different services are usually a
better choice in more complex scenarios, but also hard to manage through command-line and startup-scripts alone.

A similar discussion arises around the question whether a containerized program should run as `root`. Many developers
consider the container around everything safe enough. However, as soon as there are shared resources between containers,
more care has to be taken. Removing the superuser privilege consequently requires adjustment of file system permissions
and structuring user groups.

Container landscapes with ContainerMap
--------------------------------------
The implementation of :class:`~dockermap.map.container.ContainerMap` aims to address both aforementioned issues.

* It configures the creation and start of containers, including their dependencies.
* Shared resources (e.g. file systems, unix domain sockets) can be moved to shared volumes; permissions can be adjusted
  upon startup.

Container maps can be created empty and defined by code, updated from dictionaries, loaded from YAML, or combinations of
those methods. Every map has a name, that is set on instantiation::

    container_map = ContainerMap('new_map')

Structure
^^^^^^^^^
A :class:`~dockermap.map.container.ContainerMap` carries the following main elements:

* :attr:`~dockermap.map.container.ContainerMap.containers`: A set of container configurations.
* :attr:`~dockermap.map.container.ContainerMap.volumes`: Shared volume aliases to be used by the container configurations.
* :attr:`~dockermap.map.container.ContainerMap.host`: Host volume paths, if they are mapped from the host's file system

Their contents can be accessed like regular attributes, e.g.::

    container_map.containers.app1.binds = 'volume1'
    container_map.volumes.volume1 = '/var/log/service'
    container_map.host.volume1 = '/var/log/app1'

or in a dictionary-like syntax::

    container_map.containers['app1'].binds = 'volume1'
    container_map.volumes['volume1'] = '/var/log/service'
    container_map.host['volume1'] = '/var/log/app1'

.. NOTE::
   Elements of :attr:`~dockermap.map.container.ContainerMap.containers` do not have to be instantiated explicitly, but
   are created upon their first access. For accessing only defined container configurations, see
   :attr:`~dockermap.map.container.ContainerMap.get_existing`.

Additionally there are the following attributes:

* :attr:`~dockermap.map.container.ContainerMap.name`: All created containers will be prefixed with this.
* :attr:`~dockermap.map.container.ContainerMap.repository`: A prefix, that will be added to all image names, unless they
  already have one or start with ``/`` (i.e. are only local images).


Volumes
^^^^^^^
Typically Docker images rely on finding shared files (e.g. working data, log paths) in a specific directory.
The :attr:`~dockermap.map.container.ContainerMap.volumes` of a container map assigns aliases to those elements. It is
more or less just a simple dictionary of alias names and paths.

Host
^^^^
The :attr:`~dockermap.map.container.ContainerMap.host` is a single instance of
:class:`~dockermap.map.config.HostVolumeConfiguration`. This is very similar to
:attr:`~dockermap.map.container.ContainerMap.volumes`, but it defines paths on the host-side. Every alias used here
should also be defined container-side in :attr:`~dockermap.map.container.ContainerMap.volumes`.

Beside that, a :attr:`~dockermap.map.config.HostVolumeConfiguration` has
the optional property :attr:`~dockermap.map.config.HostVolumeConfiguration.root`. If the paths are relative paths
(i.e. they do not start with ``/``), they will be prefixed with the `root` at run-time.

Usually paths are defined as normal strings. If you intend to launch multiple
:attr:`~dockermap.map.config.ContainerConfiguration.instances` of the same container with
different host-path assignments, you can however also differentiate them as a dictionary::

    container_map.containers.app1.instances = 'instance1', 'instance2'
    ...
    container_map.host.volume1 = {
        'instance1': 'config/instance1',
        'instance2': 'config/instance2',
    }


Container configuration
^^^^^^^^^^^^^^^^^^^^^^^
Container configurations are defined within :class:`~dockermap.map.config.ContainerConfiguration` objects. They have
the following properties:

Image
"""""
The :attr:`~dockermap.map.config.ContainerConfiguration.image` simply sets the image to instantiate the container(s)
from. If :attr:`~dockermap.map.container.ContainerMap.repository` is set on the parent
:class:`~dockermap.map.container.ContainerMap`, it will be used as a prefix to the image name.

For example, if you have a local registry under `registry.example.com`, you likely do not want to name each of your
images separately as ``registry.example.com/image1``, ``registry.example.com/image2``, and so on. Instead, just set
the :attr:`~dockermap.map.config.ContainerConfiguration.repository` to ``registry.example.com`` and use image names
``image1``, ``image2`` etc.

As an exception, any image with ``/`` in its name will not be prefixed. In order to configure the `ubuntu` image,
set :attr:`~dockermap.map.config.ContainerConfiguration.image` to ``/ubuntu``.

If the image is not set at all, by default an image with the same name as the container will be attempted to use. Where
applicable, it is prefixed with the :attr:`~dockermap.map.container.ContainerMap.repository`.

.. _instances:

Instances
"""""""""
If you plan to launch containers from the same image with an identical configuration, except for paths on the host
system that are mapped to shared folders, these containers can be named as
:attr:`~dockermap.map.config.ContainerConfiguration.instances`. The instance name is appended to the default container
name on instantiation. If this property is not set, there is only one default instance.

Shared volumes
""""""""""""""
Volume paths can be set in :attr:`~dockermap.map.config.ContainerConfiguration.shares`, just like the
``VOLUME`` command in the Dockerfile or the ``-v`` argument to the command line client.
You do not need to specify host-mapped volumes here -- this is what
:attr:`~dockermap.map.config.ContainerConfiguration.binds` is for.

Volumes shared with the host
""""""""""""""""""""""""""""
References to volume aliases in :attr:`~dockermap.map.container.ContainerMap.host` are set in
:attr:`~dockermap.map.config.ContainerConfiguration.binds`, in order to make a host volume accessible to a
container. The definition is usually a list or tuple of :attr:`~dockermap.map.config.HostShare` instances. The latter
is a named tuple ``(volume, readonly)``, where the first element is the volume alias, and the second is a boolean
value indicating a read-only access.

For easier input, this can also be set as simple two-element Python tuples, dictionaries with each a single key;
strings are also valid input, which will default to write-access.

.. _shared-volumes-containers:

Volumes shared with other containers
""""""""""""""""""""""""""""""""""""
Inserting container names in :attr:`~dockermap.map.config.ContainerConfiguration.uses` is the equivalent to
the ``--volumes-from`` argument on the command line.

You can refer to other containers names on the map, or names listed in the
:attr:`~dockermap.map.config.ContainerConfiguration.attaches` property of other containers. When referencing other
container names, this container will have access to all of their shared volumes; when referencing attached volumes, only
the attached volume will be accessible. Either way, this declares a dependency of one container on the other.

.. _linked-containers:

Linked containers
"""""""""""""""""
Containers on the map can be linked together (similar to the ``--link`` argument on the command line) by assigning
one or multiple elements to :attr:`~dockermap.map.config.ContainerConfiguration.links`. As a result, the container
gains access to the network of the referenced container. This also defines a dependency of this container on the other.

Elements are set as :attr:`~dockermap.map.config.ContainerLink` named tuples, with elements ``(container, alias)``.
However, it is also possible to insert plain two-element Python tuples, single-key dictionaries, and strings. If the
alias is not set (e.g. because only a string is provided), the alias is identical to the container name, but without
the name prefix of the `ContainerMap`.

.. _attached-volumes:

Selectively sharing volumes
"""""""""""""""""""""""""""
There are multiple possibilities how a file system can be shared between containers:

* Assigning all containers the same host volume. This is the most practical approach for persistent working data.
* Sharing all volumes of one container with another. It is the most pragmatic approach for temporary
  files, e.g. pid or Unix sockets. However, this also implies access to all other shared volumes such as host paths.
* In order to restrict sharing to the relevant volumes, an extra container can be created that is shared between
  all other containers. For example, a web application server communicating with its cache over Unix domain sockets
  needs access to the latter, but not the cache's data or configuration.

Volumes for selective sharing with other containers can be generated using the
:attr:`~dockermap.map.config.ContainerConfiguration.attaches` property. It refers to an alias in
:attr:`~dockermap.map.container.ContainerMap.volumes` in order to define a path. At the same time, this becomes the
name of the extra container, and other container configurations can refer to it in the
:attr:`~dockermap.map.config.ContainerConfiguration.uses` property.

`Attached` containers are by default automatically created and launched from a minimal startable base image
`tianon/true`. They are also shared with the owning container. Since sharing data with other containers with
non-superuser privileges usually requires permission adjustments, setting
:attr:`~dockermap.map.config.ContainerConfiguration.user` starts one more temporary container (based on
`busybox`) running a ``chown`` command. Furthermore this sets the user that the current container is started with.
Similarly for :attr:`~dockermap.map.config.ContainerConfiguration.permissions`, a temporary `busybox` container performs
a ``chmod`` command on the shared container.

.. _additional-options:

Additional options
""""""""""""""""""
The properties :attr:`~dockermap.map.config.ContainerConfiguration.create_options` and
:attr:`~dockermap.map.config.ContainerConfiguration.start_options` are dictionaries of keyword arguments. They are
passed to the Docker Remote API functions in addition to the ones indirectly set by the aforementioned properties.

* The user that a container is launched with, inherited from the
  :attr:`~dockermap.map.config.ContainerConfiguration.user` configuration,
  can be overridden by setting ``user`` in :attr:`~dockermap.map.config.ContainerConfiguration.create_options`.
* Entries from ``volumes`` in :attr:`~dockermap.map.config.ContainerConfiguration.create_options` are
  added to elements of :attr:`~dockermap.map.config.ContainerConfiguration.shares` and resolved aliases from
  :attr:`~dockermap.map.config.ContainerConfiguration.binds`.
* Mappings on ``volumes_from`` in :attr:`~dockermap.map.config.ContainerConfiguration.start_options` override entries
  with identical keys (paths) generated from :attr:`~dockermap.map.config.ContainerConfiguration.uses`;
  non-corresponding keys are merged.
* Similarly, ``links`` keys set in :attr:`~dockermap.map.config.ContainerConfiguration.start_options` can override
  container links derived from :attr:`~dockermap.map.config.ContainerConfiguration.links` with the same name.
  Non-conflicting names merge.
* Containers marked with :attr:`~dockermap.map.config.ContainerConfiguration.persistent` set to ``True`` are treated
  like attached volumes: They are only started once and not removed during cleanup processes.

Start and create options can also be set via keyword arguments of
:meth:`~dockermap.map.client.MappingDockerClient.create` and :meth:`~dockermap.map.client.MappingDockerClient.start`,
in summary the order of precedence is the following:

#. Keyword arguments to the :meth:`~dockermap.map.client.MappingDockerClient.create` and
   :meth:`~dockermap.map.client.MappingDockerClient.start`;
#. :attr:`~dockermap.map.config.ContainerConfiguration.create_options` and
   :attr:`~dockermap.map.config.ContainerConfiguration.start_options`;
#. and finally the aforementioned attributes from the :class:`~dockermap.map.config.ContainerConfiguration`;

whereas single-value properties (e.g. user) are overwritten and dictionaries merge (i.e. override matching keys).

Besides overriding the generated arguments, these options can also be used for addressing features not directly
related to `Docker-Map`, e.g.::

    config = container_map.containers.app1
    config.create_options = {
        'mem_limit': '3g',  # Sets a memory limit.
    }
    config.start_options = {
        'port_bindings': {8000: 80},  # Map the container port 8000 to host port 80.
        'restart_policy': {'MaximumRetryCount': 0, 'Name': 'always'},  # Unlimited restart attempts.
    }


Instead of setting both dictionaries statically, they can also refer to a callable. This has to resolve to a
dictionary at run-time.

Input formats
"""""""""""""
On the attributes :attr:`~dockermap.map.config.ContainerConfiguration.instances`,
:attr:`~dockermap.map.config.ContainerConfiguration.shares`, :attr:`~dockermap.map.config.ContainerConfiguration.binds`,
:attr:`~dockermap.map.config.ContainerConfiguration.uses`, :attr:`~dockermap.map.config.ContainerConfiguration.links`,
and :attr:`~dockermap.map.config.ContainerConfiguration.attaches`, any assignment (property set) will be converted to
a list::

    container_map.containers.app1.uses = 'volume1'

does the same as::

    container_map.containers.app1.uses = ['volume1']

and::

    container_map.containers.app1.uses = ('volume1',)

As mentioned, additional conversions are made for :attr:`~dockermap.map.config.ContainerConfiguration.binds`
and :attr:`~dockermap.map.config.ContainerConfiguration.links`; each element in an input list or tuple is converted to
:attr:`~dockermap.map.config.HostShare` or :attr:`~dockermap.map.config.ContainerLink`. Keep this in mind when
modifying existing elements, since no automated conversion is done then. For example, for adding a host-shared volume
at run-time, use::

    container_map.containers.app1.binds.append(HostShare('volume1', False))

Creating and using container maps
---------------------------------
A map can be initialized with or updated from a dictionary. Its keys and values should be structured
in the same way as the properties of :class:`~dockermap.map.container.ContainerMap`. There are two exceptions:

* Container names with their associated configuration can be, but do not have to be wrapped inside a ``containers``
  key. Any key that is not ``volumes``, ``host``, ``repository``, or ``host_root`` is considered a potential container
  name.
* The host root path :attr:`~dockermap.map.config.HostVolumeConfiguration.root` can be set either with a ``host_root``
  key on the highest level of the dictionary, or by a ``root`` key inside the ``host`` dictionary.

For initializing a container map upon instantiation, pass the dictionary as the second argument, after the map name.
This also performs a brief integrity check, which can be deactivated by passing ``check_integrity=False`` and repeated
any time later with :meth:`~dockermap.map.container.ContainerMap.check_integrity`.

A :class:`~dockermap.map.client.MappingDockerClient` instance finally applies the container map to a Docker client. Due
to needed additional functionality in the process of creating and running containers, the latter must be an instance of
:class:`~dockermap.map.base.DockerClientWrapper`. Details of these implementations are described in
:ref:`container_client`.

.. _container_map_example:

Example
^^^^^^^
.. NOTE::
   The following example assumes that actions on containers are determined using the default policy class
   :class:`~dockermap.map.policy.resume.ResumeUpdatePolicy`.

This is a brief example, given a web server that communicates with two app instances of the same image over unix domain
sockets::

    container_map = ContainerMap('example_map', {
        'repository': 'registry.example.com',
        'host_root': '/var/lib/site',
        'web_server': { # Configure container creation and startup
            'image': 'nginx',
            'binds': {'web_config': 'ro'},
            'uses': 'app_server_socket',
            'attaches': 'web_log',
            'start_options': {
                'port_bindings': {80: 80, 443: 443},
            },
        },
        'app_server': {
            'image': 'app',
            'instances': ('instance1', 'instance2'),
            'binds': (
                {'app_config': 'ro'},
                'app_data',
            ),
            'attaches': ('app_log', 'app_server_socket'),
            'user': 2000,
            'permissions': 'u=rwX,g=rX,o=',
        },
        'volumes': { # Configure volume paths inside containers
            'web_config': '/etc/nginx',
            'web_log': '/var/log/nginx',
            'app_server_socket': '/var/lib/app/socket',
            'app_config': '/var/lib/app/config',
            'app_log': '/var/lib/app/log',
            'app_data': '/var/lib/app/data',
        },
        'host': { # Configure volume paths on the Docker host
            'web_config': 'config/nginx',
            'app_config': {
                'instance1': 'config/app1',
                'instance2': 'config/app2',
            },
            'app_data': {
                'instance1': 'data/app1',
                'instance2': 'data/app2',
            },
        },
    })

This example assumes you have two images, ``registry.example.com/nginx`` for the web server and
``registry.example.com/app`` for the application server (including the app). Inside the ``nginx`` image, the working
user is assigned to the group id ``2000``. The app server is running with a user that has the id ``2000``.

Creating a container with::

    map_client = MappingDockerClient(container_map, DockerClientWrapper('unix://var/run/docker.sock'))
    map_client.create('web_server')

results in the following actions:

#. Dependencies are checked. ``web_server`` uses ``app_server_socket``, which is attached to ``app_server``.
   Consequently, ``app_server`` will be processed first.
#. ``app_server_socket`` is created. The name of the new container is ``example_map.app_server_socket``.
#. Two instances of ``app_server`` are created with the names ``example_map.app_server.instance1`` and
   ``example_map.app_server.instance2``. Each instance is assigned a separate path on the host for ``app_data`` and
   ``app_config``. In both instances, ``app_config`` is a read-only volume.
#. ``web_server`` is created with the name ``example_map.web_server``, mapping the host volume ``web_config`` as
   read-only.

Furthermore, on calling::

    map_client.start('web_server')

#. Dependencies are resolved, just as before.
#. ``example_map.app_server_socket`` is started, so that it can share its volume.
#. Temporary containers are started and run ``chown`` and ``chmod`` on the ``app_server_socket`` volume. They are
   removed directly afterwards.
#. ``example_map.app_server.instance1`` and ``example_map.app_server.instance2`` are started and gain access to
   the volume of ``example_map.app_server_socket``.
#. ``example_map.web_server`` is started, and shares the volume of ``example_map.app_server_socket`` with the app
   server instances.
