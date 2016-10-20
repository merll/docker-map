.. _container_client:

Enhanced client functionality
=============================
The library comes with an enhanced client for some added functionality. Docker-Map is relying on that for managing
container creation and startup. One part of the client is :class:`~dockermap.map.base.DockerClientWrapper`, a wrapper
around `docker-py`'s client; another is the application of container maps in form of
:class:`~dockermap.map.container.ContainerMap` instances to this client, which is handled by
:class:`~dockermap.map.client.MappingDockerClient`.

Since version 0.2.0 it is possible to use :class:`~dockermap.map.client.MappingDockerClient` without
:class:`~dockermap.map.base.DockerClientWrapper`. The following paragraphs describe the added wrapper functionality. If
you are not interested in that, you can skip to :ref:`applying_maps`.

Wrapped functionality
---------------------
In a few methods, the original arguments and behavior of `docker-py` has been modified in
:class:`~dockermap.map.base.DockerClientWrapper`:

Building images
^^^^^^^^^^^^^^^
On the build method :meth:`~dockermap.map.base.DockerClientWrapper.build`, it is mandatory to give the new image a
name (short example in :ref:`build_image_run`). If needed, add more tags by specifying ``add_tags``. Optionally
``add_latest_tag`` can be set to ``True`` for tagging the image additionally with `latest`.

Whereas `docker-py` returns a stream, the wrapped method sends that stream to a log (see :ref:`client-logging`) and
returns the new image id, if the build has been successful. Unsuccessful builds return ``None``.

Registry access
^^^^^^^^^^^^^^^
A login to a registry server with :meth:`~dockermap.map.base.DockerClientWrapper.login` only returns ``True``, if it
has been successful, or ``False`` otherwise. Registry :meth:`~dockermap.map.base.DockerClientWrapper.pull` and
:meth:`~dockermap.map.base.DockerClientWrapper.push` actions process the stream output using
:meth:`~dockermap.map.base.DockerClientWrapper.push_log`; they return ``True`` or ``False`` depending on whether the
operation succeeded.

Added functionality
-------------------
The following methods are not part of the original `docker-py` implementation:

.. _client-logging:

Logging
^^^^^^^
Feedback from the service is processed with :meth:`~dockermap.map.base.DockerClientWrapper.push_log`. The default
implementation uses the standard logging system. Progress streams are sent using
:meth:`~dockermap.map.base.DockerClientWrapper.push_progress`, which by default is not implemented. Logs for a running
container can be shown with :meth:`~dockermap.map.base.DockerClientWrapper.push_container_logs`. Each message is
prefixed with the container name.

Building from DockerFile and DockerContext
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
In order to build files directly from :class:`~dockermap.build.dockerfile.DockerFile` and
:class:`~dockermap.build.context.DockerContext` instances,
:meth:`~dockermap.map.base.DockerClientWrapper.build_from_file` and
:meth:`~dockermap.map.base.DockerClientWrapper.build_from_context` are available. For details, see
:ref:`build_images`.

Managing images and containers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
On development machines, containers often have to be stopped, removed, and restarted. Furthermore, when repeatedly
building images, there may be a lot of unused images around.

Calling :meth:`~dockermap.map.base.DockerClientWrapper.cleanup_containers` removes all stopped containers from the
remote host. Containers that have never been started are not deleted.
:meth:`~dockermap.map.base.DockerClientWrapper.remove_all_containers` stops and removes all containers on the remote.
Use this with care outside of the development environment.

For removing images without names and tags (i.e. that show up as `none`), use
:meth:`~dockermap.map.base.DockerClientWrapper.cleanup_images`. Optionally, setting ``remove_old`` to ``True``
additionally removes images that do have names and tags, but not one with `latest`::

    client.cleanup_images(remove_old=True)

All current container names are available through :meth:`~dockermap.map.base.DockerClientWrapper.get_container_names`,
for checking if they exist. Similarly :meth:`~dockermap.map.base.DockerClientWrapper.get_image_tags` returns all
named images, but in form of a dictionary with a name-id assignment.

Storing images and resources
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The original implementations of ``copy`` (copying a resource from a container) and ``get_image`` (retrieving an image
as a tarball) are available directly, but they return a stream. Implementations of
:meth:`~dockermap.map.base.DockerClientWrapper.copy_resource` and
:meth:`~dockermap.map.base.DockerClientWrapper.save_image` allow for writing the data directly to a local file.
However, this has turned out to be very slow and may not be practical.


.. _applying_maps:

Applying container maps
-----------------------
This section provides some background information of the client functionality. The configuration and an example is
further described in :ref:`container_maps`.

Instances of :class:`~dockermap.map.client.MappingDockerClient` are usually created with a map and a client.
The former is an instance of :class:`~dockermap.map.container.ContainerMap`, the latter is
a :class:`~docker.client.Client` object. Both initializing arguments are however optional and may be
changed any time later using the properties :attr:`~dockermap.map.client.MappingDockerClient.maps`::

    from dockermap.api import DockerClientWrapper, MappingDockerClient

    map_client = MappingDockerClient(container_map, DockerClientWrapper('unix://var/run/docker.sock'))

Since version 0.2.0, also multiple maps and clients are supported. If exactly one map is provided, it is considered the
default map. That one is always used when not specified otherwise in a command (e.g. ``create``). Similarly, there can
be a default client, which is used whenever a container map or container configuration does not explicitly state a
different set of clients.

Clients are configured with :class:`~dockermap.map.config.ClientConfiguration` objects, which are passed to the
:class:`~dockermap.map.client.MappingDockerClient` constructor::

    from dockermap.api import ClientConfiguration, MappingDockerClient

    clients = {
        'client1': ClientConfiguration('host1'),
        'client2': ClientConfiguration('host2'),
        ...
    }
    map_client = MappingDockerClient([container_map1, container_map2, ...],     # Container maps as list, tuple or dict
                                     clients['client1'],                        # Default client, optional
                                     clients=clients)                           # Further clients

These clients are then used according to the :ref:`map_clients` configuration on a container map.
The default client can be referenced with the name ``__default__``.
