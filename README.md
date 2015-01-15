Docker-Map
==========

Utilities for building and managing Docker images and containers in Python.
---------------------------------------------------------------------------

Project: https://github.com/merll/docker-map

Docs: https://docker-map.readthedocs.org/en/latest/


Overview
========
This package provides additional tools for building Docker images, create containers,
connect dependent resources, and run them in development as well as production
environments.

The library builds on functionality of the Docker Remote API client for Python,
`docker-py`. Based on it, available deployment tools can be enhanced
(see [docker-fabric](https://github.com/merll/docker-fabric)) or custom orchestration
can be implemented.

Containers and their dependencies are configured object-based, through Python dictionaries,
or YAML files.

Building images
===============
Writing Dockerfiles is not hard. However, it only allows for using variable context to a
limited extent. For example, you may want to re-define directory paths in your project,
without having to adjust it in multiple places; or you keep frequently reoccurring tasks
(e.g. creating system user accounts) in your Dockerfile, and would like to use templates
rather than copy & paste.

`DockerFile`
------------
Generates a Dockerfile, that can either be saved locally or sent off to Docker
through the remote API. Supports common commands such as `addfile` (`ADD`) or `run`, but
also formats `CMD` and `ENTRYPOINT` appropriately for running a shell or exec command.

`DockerContext`
---------------
Generates a Docker context tarball, that can be sent to the remote API.
Its main purpose is to add files from `DockerFile` automatically, so that the Dockerfile
and the context tarball are consistent.


Creating, connecting, and running containers
============================================
Containers can be created easily on the command line or using the Remote API, but managing
dependencies can be tedious. Whereas the path and links may be quite individual to the
local configuration, directory paths are typically constant within the containers.
This package therefore intends to reduce repetitions of names and paths in API commands,
by introducing the following main features:

* Automatically create and assign shared volumes, where the only purpose is to share data
  between containers.
* Automatically update containers if their shared volumes are inconsistent or their image
  has been updated.
* Use alias names instead of paths to bind host volumes to container shares.
* Automatically create and start containers when their dependent containers are started.

`ContainerConfiguration`
------------------------
Keeps the elements of a configured container. Its main elements are:

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
  names.
* `links`: For container linking. Container names are translated to instance name on the map.
* `attaches`: Generates a separate container for the purpose of sharing data with another
  one, assigns file system permissions as set in `permissions` and `user`. This makes
  configuration of sockets very easy.
* `exposes`: Configures port bindings for linked containers and on host interfaces.
* `create_options` and `start_options` provide the possibility to add additional keyword
  arguments such as `command` or `entrypoint`, which are passed through to the `docker-py`
  client.

`ContainerMap`
--------------
Contains three sets of elements:

1. Container names, associated with a `ContainerConfiguration`.
2. Volumes, mapping shared directory paths to alias names.
3. Host shares, mapping host directory paths to alias names.

Clients, as defined in a `ContainerConfiguration`, can also be set globally on map level.

`ContainerConfiguration` instances and their elements can be created and used in a
dictionary-like or attribute syntax, e.g.
`container_map.containers.container_name.uses` or
`container_map.containers['container_name']['uses']`.
Volume aliases are stored in `container_map.volumes` and host binds in
`container_map.host`; they support the same syntax variations as containers.

`ClientConfiguration`
---------------------
Allows for a host-specific managment of parameters, such as service URL and timeout. For
example, the `interfaces` property translates the `exposes` setting for a configuration on each
host into a port binding argument with the local address.

`MappingDockerClient`
---------------------
Applies one or multiple `ContainerMap` instances to one or multiple Docker clients. A
container on the map can easily be created with all its dependencies by running
`client.create('container_name')`.

Running the container can be as easy as
`client.start('container_name')`
or can be enhanced with custom parameters such as
`client.start('container_name', expose={80: 80})`.

If all configuration is stored on the map, creation and start are combined in
`client.startup('container_name')`.
