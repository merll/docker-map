.. _container_landscapes:

Container scenarios
===================
Several practices have evolved around what should be part of a single container or separate. It is mainly a trade-off
between simplicity and flexibility: On one hand, if one container encloses all necessary programs, it is easier to
connect them, as they share one common file system and network. Beside security concerns, this can turn out to be
impractical on the other hand. A single container has to be maintained and updated as a single container, which
takes more time to build. In larger system landscapes monolithic containers also creates a lot of redundancy of systems
that could otherwise be shared easily, e.g. databases. Separate containers for different services have are usually a
better choice in more complex scenarios, but also hard to manage through command-line and startup-scripts alone.

A similar discussion arises around the question whether a containerized program should run as `root`. Many developers
consider the container around everything safe enough. However, as soon as there are shared resources between containers,
more care has to be taken. Removing the superuser privilege consequently requires adjustment of file system permissions
and structuring user groups.


Container landscapes with ContainerMap
--------------------------------------
The implementation of :class:`~dockermap.map.container.ContainerMap` aims to address both issues.

* It configures the creation and start of containers, including their dependencies.
* Shared resources (e.g. file systems, unix domain sockets) can be moved to shared volumes; permissions can be adjusted
  upon startup.

Structure
^^^^^^^^^
A :class:`~dockermap.map.container.ContainerMap` carries the following main elements:

* :attr:`~dockermap.map.container.ContainerMap.containers`: A set of container configurations.
* :attr:`~dockermap.map.container.ContainerMap.volumes`: Shared volume aliases to be used by the container configurations.
* :attr:`~dockermap.map.container.ContainerMap.host`: Host volume paths, if they are mapped from the host's file system

Additionally there are the following attributes:

* :attr:`~dockermap.map.container.ContainerMap.name`: All created containers will be prefixed with this.
* :attr:`~dockermap.map.container.ContainerMap.repository`: A prefix, that will be added to all image names, unless they
  already have one or start with ``/`` (i.e. are only local images).
