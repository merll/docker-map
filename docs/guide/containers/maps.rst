.. _container_maps:

Managing containers
===================
The concept of application containers has drastically increased in popularity over the past few years. Containerized
services however need to be set up in a different way: All resources (e.g. ports and file systems) need to
be shared explicitly; otherwise they are unavailable to the container or the host using them. Services that the
application depends on need to be available when the container starts. This leads to some complexity in startup
procedures that is often attempted to manage with scripts.

Container landscapes with ContainerMap
--------------------------------------
The implementation of :class:`~dockermap.map.config.main.ContainerMap` aims to address aforementioned issues.

* It configures the creation and start of containers, including their dependencies. It pulls images, creates volumes,
  and configures networks as necessary.
* Shared resources (e.g. file systems, unix domain sockets) can be moved to shared volumes; permissions can be adjusted
  upon startup.

Container maps can be created empty and defined by code, updated from dictionaries, loaded from YAML, or combinations of
those methods. Every map has a name, that is set on instantiation::

    from dockermap.api import ContainerMap

    container_map = ContainerMap('new_map')

Structure
^^^^^^^^^
A :class:`~dockermap.map.config.main.ContainerMap` carries the following main elements:

* :attr:`~dockermap.map.config.main.ContainerMap.containers`: A set of container configurations.
* :attr:`~dockermap.map.config.main.ContainerMap.volumes`: Shared volume aliases to be used by the container
  configurations, that can also be configured with common Docker options.
* :attr:`~dockermap.map.config.main.ContainerMap.host`: Host volume paths, if they are mapped from the host's file system.
* :attr:`~dockermap.map.config.main.ContainerMap.networks`: If the Docker version used supports it, allows for
  configuration of additional networks.
* :attr:`~dockermap.map.config.main.ContainerMap.groups`: Container configurations can be grouped together, so that
  actions can be performed in common.

Their contents can be accessed like regular attributes, e.g.::

    container_map.containers.app1.binds = 'volume1'
    container_map.volumes.volume1 = '/var/log/service'
    container_map.host.volume1 = '/var/log/app1'

or in a dictionary-like syntax::

    container_map.containers['app1'].binds = 'volume1'
    container_map.volumes['volume1'] = '/var/log/service'
    container_map.host['volume1'] = '/var/log/app1'

.. NOTE::
   Elements of :attr:`~dockermap.map.config.main.ContainerMap.containers` do not have to be instantiated explicitly, but
   are created upon their first access. For accessing only defined container configurations, see
   :attr:`~dockermap.map.config.main.ContainerMap.get_existing`.

Additionally there are the following attributes:

* :attr:`~dockermap.map.config.main.ContainerMap.name`: All created containers will be prefixed with this.
* :attr:`~dockermap.map.config.main.ContainerMap.repository`: A prefix, that will be added to all image names, unless they
  already have one or start with ``/`` (i.e. are only local images).
* :attr:`~dockermap.map.config.main.ContainerMap.default_domain`: The domain name that is set on new containers; it can
  be overridden by a client configuration. If none of the two are available, Docker's default is used.
* :attr:`~dockermap.map.config.main.ContainerMap.set_hostname`: For specifying a new container's host name dependent on
  the container name (in the format ``<client name>-<container name>``), this is by default set to ``True``. If set
  to ``False``, Docker automatically generates a new host name for each container.
* :attr:`~dockermap.map.config.main.ContainerMap.use_attached_parent_name`: If you would like to re-use the same volume
  aliases for :ref:`attached-volumes` or apply `inheritance`_, this changes the naming scheme of attached volume
  containers to include the name of their parent container.

Volumes
^^^^^^^
Typically Docker applications rely on finding shared files (e.g. working data, log paths) in a specific directory.
The :attr:`~dockermap.map.config.main.ContainerMap.volumes` of a container map assigns aliases to those elements. At the
same time, volumes can be configured here including the following properties:

* :attr:`~dockermap.map.config.volume.VolumeConfiguration.default_path`: The path that is used for this volume alias by
  default (i.e. unless overridden in a container configuration). This is the only property that is assigned when only
  a string is passed when creating this configuration.
* :attr:`~dockermap.map.config.volume.VolumeConfiguration.driver`: Volume drive to use, in case this is a named Docker
  volume that is shared between containers. For host volumes this has no effect. The default is ``local``.
* :attr:`~dockermap.map.config.volume.VolumeConfiguration.driver_options`: Further options to pass to the driver on
  volume creation.
* :attr:`~dockermap.map.config.volume.VolumeConfiguration.create_options`: Additional arguments for volume creation,
  that are not further connected to Docker-Map's functionality.
* :attr:`~dockermap.map.config.volume.VolumeConfiguration.user`: On volume creation, ownership of the virtual path
  is set to this user/group with a ``chown`` command. For host volumes, this has no effect. If not set, the user
  of the container configuration is used that has this one set in
  :attr:`~dockermap.map.config.container.ContainerConfiguration.attaches`, if any.
* :attr:`~dockermap.map.config.volume.VolumeConfiguration.permissions`: Similar to the
  :attr:`~dockermap.map.config.volume.VolumeConfiguration.user`, permissions on the virtual path of the volume can be
  made through this setting, and is applied using ``chmod`` on container creation.

Depending on its purpose, this can be used for configuring volumes or just for assigning default volume paths to an
alias::

    container_map.volume1 = '/var/lib/my-app/data'

is equivalent to::

    container_map.volume1 = VolumeConfiguration(default_path='/var/lib/my-app/data')


Host
^^^^
The :attr:`~dockermap.map.config.main.ContainerMap.host` is a single instance of
:class:`~dockermap.map.config.HostVolumeConfiguration`. This is very similar to
:attr:`~dockermap.map.config.main.ContainerMap.volumes`, but it defines paths on the host-side. Every alias used here
should also be defined container-side in :attr:`~dockermap.map.config.main.ContainerMap.volumes`.

Beside that, a :attr:`~dockermap.map.config.HostVolumeConfiguration` has
the optional property :attr:`~dockermap.map.config.HostVolumeConfiguration.root`. If the paths are relative paths
(i.e. they do not start with ``/``), they will be prefixed with the `root` at run-time.

Usually paths are defined as normal strings. If you intend to launch multiple
:attr:`~dockermap.map.config.container.ContainerConfiguration.instances` of the same container with
different host-path assignments, you can however also differentiate them as a dictionary::

    container_map.containers.app1.instances = 'instance1', 'instance2'
    ...
    container_map.host.volume1 = {
        'instance1': 'config/instance1',
        'instance2': 'config/instance2',
    }



Networks
^^^^^^^^
Networks can be configured with the properties as specified in the Docker API docs. The ``driver`` is usually set to
``bridge`` for custom networks (and is therefore the default). Driver options can be added in ``driver_options``.
For any parameters not supported by this configuration, ``create_options`` can be used::

    from dockermap.api import NetworkConfiguration

    container_map.networks.network1 = NetworkConfiguration(internal=True,
                                                           driver_options={
                                                               'com.docker.network.bridge.enable_icc': 'false'
                                                           })


.. _map_clients:

Clients
^^^^^^^
Since version 0.2.0, a map can describe a container structure on a specific set of clients. For example, it is possible
to run three application servers on a set of hosts, which are reverse-proxied by a single web server. This scenario
would be described using the following configuration::

    from dockermap.api import ClientConfiguration

    clients = {
        'apps1': ClientConfiguration(base_url='apps1_host', interfaces={'private': '10.x.x.11'}),
        'apps2': ClientConfiguration(base_url='apps2_host', interfaces={'private': '10.x.x.12'}),
        'apps3': ClientConfiguration(base_url='apps3_host', interfaces={'private': '10.x.x.13'}),
        'web1': ClientConfiguration(base_url='web1_host', interfaces={'private': '10.x.x.21', 'public': '178.x.x.x'}),
    }
    apps_container_map.clients = 'apps1', 'apps2', 'apps3'
    web_container_map.clients = 'web1'

The `interfaces` definition can later be used when specifying the address that a port is to be exposed on.

Clients specified within a container configuration have a higher priority than map-level definitions.

Container configuration
^^^^^^^^^^^^^^^^^^^^^^^
Container configurations are defined within :class:`~dockermap.map.config.container.ContainerConfiguration` objects. They have
the following properties:

Image
"""""
The :attr:`~dockermap.map.config.container.ContainerConfiguration.image` simply sets the image to instantiate the container(s)
from. As usual, new containers are used from the image with the ``latest`` tag, unless explicitly specified using a
colon after ithe image name, e.g. ``ubuntu:16.10``. Using the :attr:`~dockermap.map.config.main.ContainerMap.default_tag`
property on the parent map, this becomes the new default tag. For example, if you usually tag all `development` images
as ``devel`` and set :attr:`~dockermap.map.config.main.ContainerMap.default_tag` accordingly, setting
:attr:`~dockermap.map.config.container.ContainerConfiguration.image` to ``image1`` results in using the image ``image1:devel``.

If :attr:`~dockermap.map.config.main.ContainerMap.repository` is set on the parent
:class:`~dockermap.map.config.main.ContainerMap`, it will be used as a prefix to image names.

For example, if you have a local registry under `registry.example.com`, you likely do not want to name each of your
images separately as ``registry.example.com/image1``, ``registry.example.com/image2``, and so on. Instead, just set
the :attr:`~dockermap.map.config.container.ContainerConfiguration.repository` to ``registry.example.com`` and use image names
``image1``, ``image2`` etc.

As an exception, any image with ``/`` in its name will not be prefixed. In order to configure the `ubuntu` image,
set :attr:`~dockermap.map.config.container.ContainerConfiguration.image` to ``/ubuntu`` or ``/ubuntu:16.10``.

If the image is not set at all, by default an image with the same name as the container will be attempted to use. Where
applicable, it is prefixed with the :attr:`~dockermap.map.config.main.ContainerMap.repository` or enhanced with
:attr:`~dockermap.map.config.main.ContainerMap.default_tag`.

Examples, assuming the configuration name is ``app-server``:

+---------------+----------------------+-----------------+----------------------------------------+
| ``image``     | ``repository``       | ``default_tag`` | Expanded image name                    |
+===============+======================+=================+========================================+
| --            | --                   | --              | app-server:latest                      |
+---------------+                      |                 +----------------------------------------+
| image1        |                      |                 | image1:latest                          |
+---------------+----------------------+                 +----------------------------------------+
| --            | registry.example.com |                 | registry.example.com/app-server:latest |
+---------------+                      |                 +----------------------------------------+
| image1        |                      |                 | registry.example.com/image1:latest     |
+---------------+----------------------+-----------------+----------------------------------------+
| --            | --                   | devel           | app-server:devel                       |
+---------------+                      |                 +----------------------------------------+
| image1        |                      |                 | image1:devel                           |
+---------------+----------------------+                 +----------------------------------------+
| --            | registry.example.com |                 | registry.example.com/app-server:devel  |
+---------------+                      |                 +----------------------------------------+
| image1        |                      |                 | registry.example.com/image1:devel      |
+---------------+                      |                 +----------------------------------------+
| /image1       |                      |                 | image1:devel                           |
+---------------+                      |                 +----------------------------------------+
| image1:one    |                      |                 | registry.example.com/image1:one        |
+---------------+                      |                 +----------------------------------------+
| /image1:two   |                      |                 | image1:two                             |
+---------------+----------------------+-----------------+----------------------------------------+

.. _instances:

Instances
"""""""""
If you plan to launch containers from the same image with an identical configuration, except for paths on the host
system that are mapped to shared folders, these containers can be named as
:attr:`~dockermap.map.config.container.ContainerConfiguration.instances`. The instance name is appended to the default container
name on instantiation. If this property is not set, there is only one default instance.

.. _container-clients:

Stop timeout
""""""""""""
When stopping or restarting a container, Docker sends a ``SIGTERM`` signal to its main process. After a timeout period,
if the process is still not shut down, it receives a ``SIGKILL``. Some containers, e.g. database servers, may take
longer than Docker's default timeout of 10 seconds. For this purpose
:attr:`~dockermap.map.config.container.ContainerConfiguration.stop_timeout` can be set to a higher value.

.. tip::

    This setting is also available on client level. The container configuration takes precedence over the client
    setting.

Where the Docker host supports it (API version >=1.25), and provided you are using version 2.x of the Docker Python
library, this setting is also passed during container creation so that manually stopping a container (e.g. through
CLI ``docker stop <container>``) is making use of this setting as well. Otherwise this only applies when stopping or
restarting containers through Docker-Map.

Stop signal
"""""""""""
Not all applications handle ``SIGTERM`` in a way that is expected by Docker, so setting
:attr:`~dockermap.map.config.container.ContainerConfiguration.stop_timeout` may not be sufficient. For example, PostgreSQL
on a ``SIGTERM`` signal enters `Smart Shutdown <http://www.postgresql.org/docs/9.4/static/server-shutdown.html>`_
mode, preventing it from accepting new connections, but not interrupting existing ones either, which can lead to a
longer shutdown time than expected.

In this case you can use a more appropriate signal, e.g. ``SIGINT``. Set either the text representation (``SIGINT``,
``SIGQUIT``, ``SIGHUP`` etc.) or the numerical constant (see the `signal` man page) in the property
:attr:`~dockermap.map.config.container.ContainerConfiguration.stop_signal`. It will be considered during stop and restart actions
of the container. As usual, ``SIGKILL`` will be used after, if necessary.

Where the Docker host supports it (API version >=1.21), this setting is also passed during container creation so that
manually stopping a container (e.g. through CLI ``docker stop <container>``) is making use of this setting. Otherwise
this only applies when stopping or restarting containers through Docker-Map.

Shared volumes
""""""""""""""
Volume paths can be set in :attr:`~dockermap.map.config.container.ContainerConfiguration.shares`, just like the
``VOLUME`` command in the Dockerfile or the ``-v`` argument to the command line client.
You do not need to specify host-mapped volumes here -- this is what
:attr:`~dockermap.map.config.container.ContainerConfiguration.binds` is for.

Volumes shared with the host
""""""""""""""""""""""""""""
Volumes from the host, that are accessed by a single container, can be configured in one step::

    container_map.containers.app1.binds = {'container_path': ('host_path', 'ro')}

For making the host volume accessible to multiple containers, it may be more practical to use an volume alias:

#. Create an alias in :attr:`~dockermap.map.config.main.ContainerMap.volumes`, specifying the path inside the container.
#. Add the host volume path using the same alias under :attr:`~dockermap.map.config.main.ContainerMap.host`.
#. Then this alias can be used in the :attr:`~dockermap.map.config.container.ContainerConfiguration.binds` property of one or
   more containers on the map.

Example::

    container_map.volumes.volume1 = '/var/log/service'
    container_map.volumes.volume2 = '/var/run/service'
    container_map.host.volume1 = '/var/app1/log'
    container_map.host.volume2 = '/var/app1/run'
    # Add volume1 as read-write, make volume2 read-only.
    container_map.containers.app1.binds = ['volume1', ('volume2', True)]

The definition in :attr:`~dockermap.map.config.main.ContainerMap.host` is usually a list or tuple of
:attr:`~dockermap.map.config.SharedVolume` instances.

For easier input, this can also be set as simple two-element Python tuples, dictionaries with each a single key;
strings are also valid input, which will default to read-only-access (except ``rw``).

The following are considered the same for a direct volume assignment (without alias), for read-only access::

    container_map.containers.app1.binds = {'container_path': ('host_path', 'ro')}
    container_map.containers.app1.binds = {'container_path': ('host_path', 'true')}
    container_map.containers.app1.binds = [('container_path', 'host_path', True)]
    container_map.containers.app1.binds = (['container_path', ('host_path', True)], )


Using aliases and two different forms of access, the following has an identical result::

    container_map.containers.app1.binds = {'volume1': 'rw', 'volume2': True}
    container_map.containers.app1.binds = ['volume1', ('volume2', True)]
    container_map.containers.app1.binds = [['volume1'], ('volume2', 'ro')]


.. NOTE::

   Volume paths on the host are prefixed with :attr:`~dockermap.map.config.HostVolumeConfiguration.root`, if the latter
   is set and the container path does not start with a slash. This also applies to directly-assigned volume paths
   without alias.


.. _shared-volumes-containers:

Volumes shared with other containers
""""""""""""""""""""""""""""""""""""
Inserting container names in :attr:`~dockermap.map.config.container.ContainerConfiguration.uses` is the equivalent to
the ``--volumes-from`` argument on the command line.

You can refer to other containers names on the map, or names listed in the
:attr:`~dockermap.map.config.container.ContainerConfiguration.attaches` property of other containers. When referencing other
container names, this container will have access to all of their shared volumes; when referencing attached volumes, only
the attached volume will be accessible. Either way, this declares a dependency of one container on the other.

Like :attr:`~dockermap.map.config.main.ContainerMap.host`, input to
:attr:`~dockermap.map.config.main.ContainerMap.uses` can be provided as tuples, dictionaries, or single strings, which
are converted into lists of :attr:`~dockermap.map.config.SharedVolume` tuples.

.. _attached-volumes:

Selectively sharing volumes
"""""""""""""""""""""""""""
There are multiple possibilities how a file system can be shared between containers:

* Assigning all containers the same host volume. This is the most practical approach for persistent working data.
* Sharing all volumes of one container with another. It is the most pragmatic approach for temporary
  files, e.g. pid or Unix sockets. However, this also implies access to all other shared volumes such as host paths.
* Specific volumes can be shared one by one. For example, a web application server communicating with its cache over
  Unix domain sockets needs access to the latter, but not the cache's data or configuration. In more recent releases
  (since API 1.21), Docker supports named volumes for this purpose. On older releases, Docker-Map emulates this behavior
  by creating an extra container that shares a single volume.

Volumes for selective sharing with other containers can be created using the
:attr:`~dockermap.map.config.container.ContainerConfiguration.attaches` property. It refers to an alias in
:attr:`~dockermap.map.config.main.ContainerMap.volumes` in order to define a path and optionally the configuration.
At the same time, this becomes the name of the volume (or extra container), and other container configurations can
refer to it in the :attr:`~dockermap.map.config.container.ContainerConfiguration.uses` property.

Actually using :attr:`~dockermap.map.config.container.ContainerConfiguration.attaches` and
:attr:`~dockermap.map.config.container.ContainerConfiguration.uses` is just like using the ``-v`` or
``--volumes-from`` on the command line, but this concept implies that one container *owns* the volume and provides
data, a socket file, or something else there for other containers to use.

In the aforementioned emulation pattern, `attached` containers are by default automatically created and launched from
a minimal startable base image `tianon/true`. They are also shared with the owning container::

    container_map.volumes.volume1 = '/var/data1'
    container_map.volumes.volume2 = '/var/more_data'
    container_map.host.volume1 = '/var/app1/data1'
    container_map.containers.app1.binds = 'volume1'
    container_map.containers.app1.attaches = 'volume2'
    ...
    # app2 inherits all shared volumes from app1
    container_map.containers.app2.uses = 'app1'
    # app3 only gains access to 'volume2'
    container_map.containers.app3.uses = 'volume2'

Sharing data with other containers with non-superuser privileges usually requires permission adjustments. Setting
:attr:`~dockermap.map.config.container.ContainerConfiguration.user` starts one more temporary container (based on `busybox`)
running a ``chown`` command. Furthermore this sets the user that the current container is started with.
Similarly for :attr:`~dockermap.map.config.container.ContainerConfiguration.permissions`, the temporary `busybox` container
performs a ``chmod`` command on the shared container. If the client supports running local commands via a method
``run_cmd``, instead of running the temporary container, ``chmod``  and ``chown`` will be run on the mounted volume path
of the Docker host.

.. _linked-containers:

Linked containers
"""""""""""""""""
Containers on the map can be linked together (similar to the ``--link`` argument on the command line) by assigning
one or multiple elements to :attr:`~dockermap.map.config.container.ContainerConfiguration.links`. As a result, the container
gains access to the network of the referenced container. This also defines a dependency of this container on the other.

Elements are set as :attr:`~dockermap.map.config.ContainerLink` named tuples, with elements ``(container, alias)``.
However, it is also possible to insert plain two-element Python tuples, single-key dictionaries, and strings. If the
alias is not set (e.g. because only a string is provided), the alias is identical to the container name, but without
the name prefix of the `ContainerMap`.

.. _exposed-ports:

Exposed ports
"""""""""""""
Containers may expose networking ports to other services, either to :ref:`linked-containers` or to a host networking
interface. The :attr:`~dockermap.map.config.container.ContainerConfiguration.exposes` property helps setting the ports and
bindings appropriately during container creation and start.

The configuration is set either through a list or tuple of the following:

* a single string or integer - exposes a port only to a linked container;
* a pair of string / integer values - publishes the exposed port (1) to the host's port (2) on all interfaces;
* a pair of string / integer values, followed by a string - publishes the exposed port (1) to the host's port (2) on
  the interface alias name (3), which is substituted with the interface address for that interface defined by the client
  configuration;
* additionally a fourth element - a boolean value - indicating whether it is an IPv6 address to be published. The
  default (``False``) is to use the IPv4 address from the client configuration of the interface alias in (3).

The publishing port, interface, and IPv6 flag can also be placed together in a nested tuple, and the entire
configuration accepts a dictionary as input. All combinations are converted to :attr:`~dockermap.map.config.PortBinding`
tuples with the elements ``(exposed_port, host_port, interface, ipv6)``.

Examples::

    ## Exposes

    clients = {
        'client1': ClientConfiguration({
            'base_url': 'unix://var/run/docker.sock',
            'interfaces': {
                'private': '10.x.x.x',  # Example private network interface IPv4 address
                'public: '178.x.x.x',   # Example public network interface IPv4 address
            },
            'interfaces_ipv6': {
                'private': '2001:a01:a02:12f0::1',  # Example private network interface IPv6 address
            },
        }),
        ...
    })

    config = container_map.containers.app1
    config.clients = ['client1']
    config.exposes = [
        (80, 80, 'public'),           # Exposes port 80 and binds it to port 80 on the public address only.
        (9443, 443),                  # Exposes port 9443 and binds to port 443 on all addresses.
        (8000, 8000, 'private'),      # Binds port 8000 to the private network interface address.
        8111,                         # Port 8111 will be exposed only to containers that link this one.
        (8000, 80, 'private', True),  # Publishes port 8000 from the container to port 80 on the host under its private
                                      # IPv6 address.
    ]


Networking
""""""""""
Docker offers further options for controlling how containers communicate with each other. By default, it creates a new
network stack of each, but it is also possible to re-use the stack of an existing container or disable networking
entirely. The following syntax is supported by
:attr:`~dockermap.map.config.container.ContainerConfiguration.network_mode`:

* ``bridge`` or ``host`` have the same effect as when used inside ``host_config``. The former is the default, and
  creates a network interface connected to ``docker0``, whereas the latter uses the Docker host's network stack.
* Similarly, ``container:`` followed by a container name or id reuses the network of an existing container. In this
  syntax, the container is assumed not to be managed by Docker-Map and therefore dependencies are not checked. The
  same applies for ``/`` followed by a container name or id.
* Setting it to the name of another container configuration (without the map name) will re-use that container's network.
  This declares a dependency, i.e. the container referred to will be created and started before the container that is
  re-using its network. Note that if there are multiple instances, you need to specify which instance the container
  is supposed to connect to in the pattern ``<container name>.<instance name>``.
* ``disabled`` turns off networking for the container.

Starting with Docker API 1.21, there is also an additional
:attr:`~dockermap.map.config.container.ContainerConfiguration.networks` property . Configured networks can be created
and containers can be connected and disconnected during creation as well as at runtime.

For example, two containers can be connected in a network using the following setup::

    from dockermap.api import ContainerConfiguration, NetworkConfiguration
    container_map.networks.network1 = NetworkConfiguration(driver='bridge')
    container_map.container1.networks = 'network1'
    container_map.container2.networks = 'network2'


Starting either of the containers will automatically create the network before. Endpoints can also be configured in
more detail. The argument order of parameters is
* Network name,
* a list of alias names on the network: ``aliases``,
* a list of linked containers: ``links``,
* the IPv4 address to use: ``ipv4_address``,
* the IPv6 address ``ipv6_address``,
* and a list of link-local IPs ``link_local_ips``.

However, as all of the above are optional, they can also be declared explicitly:

    container_map.container1.networks = {'network1': {'ipv4': '172.17.0.5'}}

Lists as mentioned above are also accepted as single values on input and converted to a list automatically.

.. note::
    The default network ``bridge`` is only implied if nothing is set for the container. This means that a container that
    has configured networks will **not** connect to ``bridge`` by default. This means that you need to add it if
    you would like a container to use it, e.g.::

        container_map.container1.networks = {
            'network1': {'ipv4': '172.17.0.5'},
            'bridge': None,  # But it does not need explicit configuration.
        }


Commands
""""""""
By default every container is started with its pre-configured entrypoint and command. These can be overwritten in each
configuration by setting ``entrypoint`` or ``command`` in
:attr:`~dockermap.map.config.container.ContainerConfiguration.create_options`.

In addition to that, :attr:`~dockermap.map.config.container.ContainerConfiguration.exec_commands` allows for setting commands to
run directly after the container has started, e.g. for processing additional scripts. The following input formats are
considered:

* A simple command line is launched with the configured
  :attr:`~dockermap.map.config.container.ContainerConfiguration.user` of the container, or ``root`` if none has been set::

    config.exec_commands = "/bin/bash -c 'script.sh'"
    config.exec_commands = ["/bin/bash -c 'script.sh'"]

* A tuple of two elements is read as ``command line, user``. This allows for overriding the user that launches the
  command. In this case, the command line can also be a list (executeable + arguments), as allowed by the Docker API::

    config.exec_commands = [
        ("/bin/bash -c 'script1.sh'", 'root'),
        (['/bin/bash', '-c', 'script2.sh'], 'user'),
    ]

* A third element in a tuple defines when the command should be run. :const:`dockermap.map.input.ExecPolicy.RESTART`
  is the default, and starts the command each time the container is started. Setting it to
  :const:`dockermap.map.input.ExecPolicy.INITIAL` indicates that the command should only be run once at container
  creation, but not at a later time, e.g. when the container is restarted or updated::

    from dockermap.map.input import ExecPolicy
    config.exec_commands = [
        ("/bin/bash -c 'script1.sh'", 'root'),                              # Run each time the container is started.
        (['/bin/bash', '-c', 'script2.sh'], 'user', ExecPolicy.INITIAL),   # Run only when the container is created.
    ]


Inheritance
"""""""""""
Container configurations can inherit settings from others, by setting their names in
:attr:`~dockermap.map.config.container.ContainerConfiguration.extends`.

Example::

    generic_config = container_map.containers.generic
    generic_config.uses = 'volume1'
    generic_config.abstract = True               # Optional - config is not used directly.
    ext_config1 = container_map.containers.app1
    ext_config1.extends = 'generic'
    ext_config1.uses = 'volume2'                 # Actually uses ``volume1`` and ``volume2``.
    ext_config2 = container_map.containers.app2
    ext_config2.extends = 'generic'
    ext_config2.uses = 'volume3'                 # Actually uses ``volume1`` and ``volume3``.

The behavior of value inheritance from other configurations is as follows:

* Values are overridden or merged in the order that they occur in
  :attr:`~dockermap.map.config.container.ContainerConfiguration.extends`. Extensions are followed recursively in this process.
* Simple values, e.g. :attr:`~dockermap.map.config.container.ContainerConfiguration.image`, are inherited from the other
  configurations and overridden in the extension.
* Single-value lists, e.g. those of :attr:`~dockermap.map.config.container.ContainerConfiguration.clients` or
  :attr:`~dockermap.map.config.container.ContainerConfiguration.uses`, are merged so that they contain the union of all values.
* Multi-value lists and dictionaries are merged together by their first value or their key, where applicable. For
  example, using the same local path in :attr:`~dockermap.map.config.container.ContainerConfiguration.binds` will use the last
  host path and read-only flag set in the order of inheritance. Similarly,
  :attr:`~dockermap.map.config.container.ContainerConfiguration.create_options` are merged so that they contain the union of
  all values, overriding identical keys in the extended configurations.

.. note::
    Usually :attr:`~dockermap.map.config.container.ContainerConfiguration.attached` containers need to have unique names across
    multiple configurations on the same map. By default their naming on these containers follows the scheme
    ``<map name>.<attached volume alias>``, which could become ambiguous when extending a configuration with attached
    volumes. When setting :attr:`~dockermap.map.config.main.ContainerMap.use_attached_parent_name` to ``True``, the
    naming scheme becomes ``<map name>.<parent container name>.<attached volume alias>``, leading to unique container
    names again. In :attr:`~dockermap.map.config.container.ContainerConfiguration.uses`, you then need to refer to containers
    by ``<parent container name>.<attached volume alias>``.

    Example::

        container_map.use_attached_parent_name = True
        generic_config = container_map.containers.generic
        generic_config.attaches = 'volume1'
        ext_config = container_map.containers.app1
        ext_config.extends = 'generic'
        ext_config.uses = 'volume2'
        ref_config = container_map.containers.test
        ref_config.uses = ['app1.volume1', 'volume2']  # Now needs to specify the container for attached volume.


.. _additional-options:

Additional options
""""""""""""""""""
The properties :attr:`~dockermap.map.config.container.ContainerConfiguration.create_options` and
:attr:`~dockermap.map.config.container.ContainerConfiguration.host_config` are dictionaries of keyword arguments. They are
passed to the Docker Remote API functions in addition to the ones indirectly set by the aforementioned properties.

* The user that a container is launched with, inherited from the
  :attr:`~dockermap.map.config.container.ContainerConfiguration.user` configuration,
  can be overridden by setting ``user`` in :attr:`~dockermap.map.config.container.ContainerConfiguration.create_options`.
* Entries from ``volumes`` in :attr:`~dockermap.map.config.container.ContainerConfiguration.create_options` are
  added to elements of :attr:`~dockermap.map.config.container.ContainerConfiguration.shares` and resolved aliases from
  :attr:`~dockermap.map.config.container.ContainerConfiguration.binds`.
* Mappings on ``volumes_from`` in :attr:`~dockermap.map.config.container.ContainerConfiguration.host_config` override entries
  with identical keys (paths) generated from :attr:`~dockermap.map.config.container.ContainerConfiguration.uses`;
  non-corresponding keys are merged.
* Similarly, ``links`` keys set in :attr:`~dockermap.map.config.container.ContainerConfiguration.host_config` can override
  container links derived from :attr:`~dockermap.map.config.container.ContainerConfiguration.links` with the same name.
  Non-conflicting names merge.
* Containers marked with :attr:`~dockermap.map.config.container.ContainerConfiguration.persistent` set to ``True`` are treated
  like attached volumes: They are only started once and not removed during cleanup processes.

Start and create options can also be set via keyword arguments of
:meth:`~dockermap.map.client.MappingDockerClient.create` and :meth:`~dockermap.map.client.MappingDockerClient.start`,
in summary the order of precedence is the following:

#. Keyword arguments to the :meth:`~dockermap.map.client.MappingDockerClient.create` and
   :meth:`~dockermap.map.client.MappingDockerClient.start`;
#. :attr:`~dockermap.map.config.container.ContainerConfiguration.create_options` and
   :attr:`~dockermap.map.config.container.ContainerConfiguration.host_config`;
#. and finally the aforementioned attributes from the :class:`~dockermap.map.config.container.ContainerConfiguration`;

whereas single-value properties (e.g. user) are overwritten and dictionaries merge (i.e. override matching keys).

.. note::
   Setting :attr:`~dockermap.map.config.container.ContainerConfiguration.start_options` has the same effect as
   :attr:`~dockermap.map.config.container.ContainerConfiguration.host_config`. The API version reported by the Docker client
   decides whether the recommended HostConfig dictionary is used during container creation (>= v1.15), or
   if additional keyword arguments are passed during container start.

Besides overriding the generated arguments, these options can also be used for addressing features not directly
related to `Docker-Map`, e.g.::

    config = container_map.containers.app1
    config.create_options = {
        'mem_limit': '3g',  # Sets a memory limit.
    }
    config.host_config = {
        'restart_policy': {'MaximumRetryCount': 0, 'Name': 'always'},  # Unlimited restart attempts.
    }


Instead of setting both dictionaries statically, they can also refer to a callable. This has to resolve to a
dictionary at run-time.

.. note::
   It is discouraged to overwrite paths of volumes that are otherwise defined via ``uses`` and ``binds``, as well as
   exposed ports as set via ``exposes``. The default policy for updating containers will not be able to detect reliably
   whether a running container is consistent with its configuration object.

Input formats
"""""""""""""
On the attributes
:attr:`~dockermap.map.config.container.ContainerConfiguration.extends`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.instances`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.shares`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.binds`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.attaches`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.uses`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.links`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.exposes`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.networks`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.exec_commands`, and
:attr:`~dockermap.map.config.container.ContainerConfiguration.clients`,
any input value that is not a list will be converted into one::

    container_map.containers.app1.uses = 'volume1'

does the same as::

    container_map.containers.app1.uses = ['volume1']

and::

    container_map.containers.app1.uses = ('volume1',)

Additional conversions are made for
:attr:`~dockermap.map.config.container.ContainerConfiguration.binds`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.attaches`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.uses`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.links`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.exposes`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.networks`,
:attr:`~dockermap.map.config.container.ContainerConfiguration.exec_commands`, and
:attr:`~dockermap.map.config.container.ContainerConfiguration.healthcheck`;
each element (where applicable, i.e. each list item) is converted into a named tuple
:class:`~dockermap.map.input.SharedVolume`,
:class:`~dockermap.map.input.HostVolume`,
:class:`~dockermap.map.input.UsedVolume`,
:class:`~dockermap.map.input.ContainerLink`,
:class:`~dockermap.map.input.PortBinding`,
:class:`~dockermap.map.input.NetworkEndpoint`,
:class:`~dockermap.map.input.ExecCommand`, or
:class:`~dockermap.map.input.HealthCheck`.

This conversion takes places place, together with some input validation, if
:meth:`~dockermap.map.config.ConfigurationObject.clean` is called directly or indirectly through any of
:meth:`~dockermap.map.config.ConfigurationObject.as_dict`,
:meth:`~dockermap.map.config.ConfigurationObject.merge_from_dict`,
:meth:`~dockermap.map.config.ConfigurationObject.merge_from_obj`, or
:meth:`~dockermap.map.config.ConfigurationObject.update_from_obj`.
Since the merge-methods are also used before resolving container dependencies, this is done implicitly before invoking
any command on container maps.

Creating and using container maps
---------------------------------
A map can be initialized with or updated from a dictionary. Its keys and values should be structured
in the same way as the properties of :class:`~dockermap.map.config.main.ContainerMap`. There are two exceptions:

* Container names with their associated configuration can be, but do not have to be wrapped inside a ``containers``
  key. Any key that is not ``volumes``, ``host``, ``repository``, or ``host_root`` is considered a potential container
  name.
* The host root path :attr:`~dockermap.map.config.HostVolumeConfiguration.root` can be set either with a ``host_root``
  key on the highest level of the dictionary, or by a ``root`` key inside the ``host`` dictionary.

For initializing a container map upon instantiation, pass the dictionary as the second argument, after the map name.
This also performs a brief integrity check, which can be deactivated by passing ``check_integrity=False`` and repeated
any time later with :meth:`~dockermap.map.config.main.ContainerMap.check_integrity`. In case of failure, it raises a
:class:`~dockermap.map.container.MapIntegrityError`.

A :class:`~dockermap.map.client.MappingDockerClient` instance finally applies the container map to a Docker client. This
can be a an instance of the Docker Remote API client. For added logging and additional functionality, using an instance
of :class:`~dockermap.map.base.DockerClientWrapper` is recommended. Details of these implementations are described in
:ref:`container_client`.

.. _container_map_example:

Example
^^^^^^^
This is a brief example, given a web server that communicates with two app instances of the same image over unix domain
sockets::

    from dockermap.api import ContainerMap

    container_map = ContainerMap('example_map', {
        'repository': 'registry.example.com',
        'host_root': '/var/lib/site',
        'web_server': { # Configure container creation and startup
            'image': 'nginx',
            # If volumes are not shared with any other container, assigning
            # an alias in "volumes" is possible, but not necessary:
            'binds': {'/etc/nginx': ('config/nginx', 'ro')},
            'uses': 'app_server_socket',
            'attaches': 'web_log',
            'exposes': {
                80: 80,
                443: 443,
            }
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
            'web_log': '/var/log/nginx',
            'app_server_socket': '/var/lib/app/socket',
            'app_config': '/var/lib/app/config',
            'app_log': '/var/lib/app/log',
            'app_data': '/var/lib/app/data',
        },
        'host': { # Configure volume paths on the Docker host
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

    from dockermap.api import DockerClientWrapper, MappingDockerClient

    map_client = MappingDockerClient(container_map, DockerClientWrapper('unix://var/run/docker.sock'))
    map_client.create('web_server')

results in the following actions:

#. Dependencies are checked. ``web_server`` uses ``app_server_socket``, which is attached to ``app_server``.
   Consequently, ``app_server`` will be processed first.
#. ``app_server_socket`` is created. The name of the new container is ``example_map.app_server_socket``.
#. Two instances of ``app_server`` are created with the names ``example_map.app_server.instance1`` and
   ``example_map.app_server.instance2``. Each instance is assigned a separate path on the host for ``app_data`` and
   ``app_config``. In both instances, ``app_config`` is a read-only volume.
#. ``web_server`` is created with the name ``example_map.web_server``, mapping the host path
   ``/var/lib/site/config/nginx`` as read-only. Ports 80 and 443 are exposed.

Furthermore, on calling::

    map_client.start('web_server')

#. Dependencies are resolved, just as before.
#. ``example_map.app_server_socket`` is started, so that it can share its volume.
#. Temporary containers are started and run ``chown`` and ``chmod`` on the ``app_server_socket`` volume. They are
   removed directly afterwards.
#. ``example_map.app_server.instance1`` and ``example_map.app_server.instance2`` are started and gain access to
   the volume of ``example_map.app_server_socket``.
#. ``example_map.web_server`` is started, and shares the volume of ``example_map.app_server_socket`` with the app
   server instances. Furthermore it maps exposed ports 80 and 443 to all addresses of the host, making them available
   to public access.

Both commands can be combined by simply running::

    map_client.startup('web_server')
