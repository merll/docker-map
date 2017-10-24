Docker-Map
==========

Managing Docker images, containers, and their dependencies in Python.
---------------------------------------------------------------------

Project: https://github.com/merll/docker-map

Docs: https://docker-map.readthedocs.io/en/latest/


Overview
========
This package provides tools for building Docker images, create containers,
connect dependent resources, and run them in development as well as production
environments.

The library builds on functionality of the Docker Remote API client for Python,
`docker-py`. Its main target is to reduce the repetitive and error-prone code that is
required for creating and connecting containers in a non-trivial stack. It can be used
standalone for custom orchestration or for enhancing available deployment / remote
execution utilities (see [Docker-Fabric](https://github.com/merll/docker-fabric),
[Salt Container-Map](https://github.com/merll/salt-container-map)).

Containers and their dependencies are configured object-based, through Python dictionaries,
or YAML files.

Building images
===============
Writing Dockerfiles is not hard. However, it only allows for using variable context to a
limited extent. For example, you may want to re-define directory paths in your project,
without having to adjust it in multiple places; or you keep frequently reoccurring tasks
(e.g. creating system user accounts) in your Dockerfile, and would like to use templates
rather than copy & paste.

Dockerfiles
-----------
A `DockerFile` object generates a Dockerfile, that can either be saved locally or sent
off to Docker through the remote API. Supports common commands such as `addfile` (`ADD`)
or `run`, but also formats `CMD` and `ENTRYPOINT` appropriately for running a shell or
exec command.

Docker file context
-------------------
`DockerContext` generates a Docker context tarball, that can be sent to the remote API.
Its main purpose is to add files from `DockerFile` automatically, so that the Dockerfile
and the context tarball are consistent.


Creating, connecting, and running containers
============================================
This package reduces repetitions of names and paths in API commands, by introducing the
following main features:

* Automatically create, configure, and assign shared volumes.
* Automatically update containers if their shared volumes are inconsistent, their image,
  or their configuration has been updated.
* Use alias names instead of paths to bind host volumes to container shares.
* Automatically create and start containers when their dependent containers are started.

Container configuration
-----------------------
`ContainerConfiguration` objects keep the elements of a configured container. Their main
elements are:

* `image`: Docker image to base the container on (default is identical to container name).
* `clients`: Optional list of clients to run the identical container configuration on.
* `instances`: Can generate multiple instances of a container with varying host mappings;
  by default there is one main instance of each container.
* `shares`: Volumes that are simply shared by the container, only for the purpose of
  keeping data separate from the container instance, or for linking the entire container
  to another.
* `binds`: Host volume mappings. Uses alias names instead of directory paths.
* `uses`: Can be names of other containers, or volumes shared by another volume through
  `attaches`. Has the same effect as the `volumes_from` argument in the API, but using alias
  names and automatically resolving these to paths.
* `links`: For container linking. Container names are translated to instance name on the map.
* `attaches`: Generates a separate container for the purpose of sharing data with another
  one, assigns file system permissions as set in `permissions` and `user`. This makes
  configuration of sockets very easy.
* `exposes`: Configures port bindings for linked containers and on host interfaces.
* `exec_commands`: Launches commands on containers after they have been created and started.
* `create_options` and `host_config` provide the possibility to add further keyword
  arguments such as `command` or `entrypoint`, which are passed through to the `docker-py`
  client.

Container maps
--------------
`ContainerMap` objects contain three sets of elements:

1. Container names, each associated with a `ContainerConfiguration`.
2. Volumes, mapping shared directory paths to alias names.
3. Host shares, mapping host directory paths to alias names.

Clients, as defined in a `ContainerConfiguration`, can also be set globally on map level.

`ContainerConfiguration` instances and their elements can be created and used in a
dictionary-like or attribute syntax, e.g.
`container_map.containers.container_name.uses` or
`container_map.containers['container_name']['uses']`.
Volume aliases are stored in `container_map.volumes` and host binds in
`container_map.host`; they support the same syntax variations as containers.

Client configuration
--------------------
`ClientConfiguration` objects allow for a host-specific management of parameters, such as
service URL and timeout. For example, the `interfaces` property translates the `exposes`
setting for a configuration on each host into a port binding argument with the local
address.

Combining the elements
----------------------
`MappingDockerClient` applies one or multiple `ContainerMap` instances to one or
multiple Docker clients. A container on the map can easily be created with all its
dependencies by running `client.create('container_name')`.

Running the container can be as easy as
`client.start('container_name')`
or can be enhanced with custom parameters such as
`client.start('container_name', expose={80: 80})`.

If all configuration is stored on the map, creation and start are combined in
`client.startup('container_name')`.
