.. Docker-Map documentation master file, created by
   sphinx-quickstart on Mon Sep  1 21:11:17 2014.

Welcome to Docker-Map's documentation!
======================================

Docker-Map enhances docker-py_, the Docker Remote API client library for Python. It provides a set of utilities for
building Docker images, create containers, connect dependent resources, and run them in development as well as
production environments.

For connections through SSH tunnels, command-line tools, and additional deployment utilities, see Docker-Fabric_.

The project is hosted on GitHub_.

Features
========

* Configuration of container landscapes, including dependencies between containers, networks, and volumes.
* Update check of containers, volumes, and networks against their running configuration. Consistency check of shared
  volume paths and re-creation of inconsistent or outdated containers.
* Utility client functions. Some of these (e.g. ``cleanup_containers``) have also been implemented on later versions of
  Docker directly; however this library can still provide more fine-grained control.
* Creation of complex `Dockerfile`'s through Python code.
* Simplified transfer of build resources (Context) to the Remote API.

Comparison to Compose
=====================
The functionality is quite similar to Docker Compose. When development of this library started, a predecessor of Compose
was known as *Fig*. Docker-Map was mainly developed for the following reasons:

* *Docker-Map* is intended to provide an API that could be embedded into other available systems such as
  configuration management. This implies that configuration can be implemented through code (although YAML input is also
  available) and functions can be invoked through Python directly.
* *Docker-Map* is not a command-line utility, and it can operate on multiple clients. For example Docker-Fabric_ is one
  implementation that connect to other clients via SSH, but can also run on the same machine.
* *Fig* and also its successor *Compose* target development and staging environments. *Docker-Map* aims to handle
  staging to production environments by allowing for embedding external variables, e.g. from configuration management.
  Although it can be combined with other tools to be suitable for development and CI, *Compose* is more common to use
  and might be the first choice there.

Contents
========

.. toctree::
   :maxdepth: 2
   
   installation
   start

   guide/images/dockerfiles
   guide/images/context
   guide/shortcuts
   guide/containers/client
   guide/containers/maps
   guide/containers/actions
   guide/containers/yaml
   guide/containers/advanced

   changes


Status
======
Docker-Map is being used for small-scale deployment scenarios in test and production.


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. _docker-py: https://github.com/docker/docker-py
.. _Docker-Fabric: https://github.com/merll/docker-fabric
.. _GitHub: https://github.com/merll/docker-map
