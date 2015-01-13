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
name (short example in :ref:`build_image_run`). Optionally ``add_latest_tag`` can be set to ``True`` for tagging the
image additionally with `latest`. Whereas `docker-py` returns a stream, the wrapped method sends that stream to a log
(see :ref:`client-logging`) and returns the new image id, if the build has been
successful. Unsuccessful builds return ``None``.

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

    map_client = MappingDockerClient(container_map, DockerClientWrapper('unix://var/run/docker.sock'))

Since version 0.2.0, also multiple maps and clients are supported. If exactly one map is provided, it is considered the
default map. That one is always used when not specified otherwise in a command (e.g. ``create``). Similarly, there can
be a default client, which is used whenever a container map or container configuration does not explicitly state a
different set of clients.

Clients are configured with :class:`~dockermap.map.config.ClientConfiguration` objects, which are passed to the
:class:`~dockermap.map.client.MappingDockerClient` constructor::

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

:class:`~dockermap.map.client.MappingDockerClient` uses a policy class, that transforms the container configurations
and their current state into actions on the client, along with keyword arguments accepted by `docker-py`.
The default, :class:`~dockermap.map.policy.resume.ResumeUpdatePolicy` supports the following methods.

* :meth:`~dockermap.map.client.MappingDockerClient.create` resolves all dependency containers to be created prior to
  the current one. First, `attached` volumes are created (see :ref:`attached-volumes`) of the dependency containers.
  Then the client creates dependency containers and the requested container. Existing containers are not re-created.
* Similarly, :meth:`~dockermap.map.client.MappingDockerClient.start` first launches dependency containers' `attached`
  volumes, then dependencies themselves, and finally the requested container. Running, `persistent`, and `attached`,
  containers are not restarted if they have exited.
* :meth:`~dockermap.map.client.MappingDockerClient.restart` only restarts the selected container.
* :meth:`~dockermap.map.client.MappingDockerClient.stop` stops the current container and containers that depend on it.
* :meth:`~dockermap.map.client.MappingDockerClient.remove` removes containers and their dependents, but does not
  remove attached volumes.
* :meth:`~dockermap.map.client.MappingDockerClient.startup`, along the dependency path,

  * removes containers with unrecoverable errors (currently code ``-127``, but may be extended as needed);
  * creates missing containers; if an attached volume is missing, the parent container is restarted;
  * and starts non-running containers (like `start`).
* :meth:`~dockermap.map.client.MappingDockerClient.shutdown` simply combines
  :meth:`~dockermap.map.client.MappingDockerClient.stop` and :meth:`~dockermap.map.client.MappingDockerClient.remove`.
* :meth:`~dockermap.map.client.MappingDockerClient.update` checks along the dependency path for outdated containers or
  container connections. In more detail, containers are removed, re-created, and restarted if any of the following
  applies:

  * The image id from existing container is compared to the current id of the image as specified in the container
    configuration. If it does not match, the container is re-created based on the new image.
  * Linked containers, as declared on the map, are compared to the current container's runtime configuration. If any
    container is missing or the linked alias mismatches, the dependent container is re-created and restarted.
  * The virtual filesystem path of attached containers and other shared volumes is compared to dependent
    containers' paths. In case of a mismatch, the latter is updated.

  For ensuring the integrity, all missing containers are created and started along the dependency path.

In order to see what defines a dependency, see :ref:`shared-volumes-containers` and :ref:`linked-containers`.

Additional keyword arguments to the ``start`` and ``create`` methods of the client are passed through; the order of
precedence towards the :class:`~dockermap.map.config.ContainerConfiguration` is further detailed in
:ref:`additional-options`. Example::

    map_client.start('web_server', restart_policy={'MaximumRetryCount': 0, 'Name': 'always'})

For limiting effects to particular :ref:`instances` of a container configuration, all these methods accept an
``instances`` argument, where one or multiple instance names can be specified. By implementing a custom subclass of
:class:`~dockermap.map.client.policy.base.BasePolicy`, the aforementioned behavior can be further adjusted to
individual needs.

Note that :class:`~dockermap.map.client.MappingDockerClient` caches names of existing containers and images for
speeding up operations. The cache is flushed automatically when the
:attr:`~dockermap.map.base.MappingDockerClient.policy_class` property is set. However, when changes (e.g. creating or
removing containers) are made directly, the name cache should be reset with
:meth:`~dockermap.map.client.MappingDockerClient.refresh_names`.

Besides aforementioned methods, you can define custom container actions such as ``custom`` and run the using
:meth:`~dockermap.map.client.MappingDockerClient.call` with the action name as the first argument. For this purpose you
have to implement a policy class with a method ``custom_action`` with the first arguments `container map name`,
`container configuration name`, and `instances`. Further keyword arguments are passed through.
