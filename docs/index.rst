.. Docker-Map documentation master file, created by
   sphinx-quickstart on Mon Sep  1 21:11:17 2014.

Welcome to Docker-Map's documentation!
======================================

Docker-Map enhances docker-py_, the Docker Remote API client library for Python. It provides a set of utilities for
building Docker images, create containers, connect dependent resources, and run them in development as well as
production environments.

For connections through SSH tunnels and additional deployment utilities, see Docker-Fabric_.

The project is hosted on GitHub_.

Features
========

* Creation of complex `Dockerfile`'s through Python code, including variables.
* Simplified transfer of build resources (Context) to the Remote API.
* Utility client functions.
* Configuration of container creation and start environments, including dependencies.
* Usage of volume aliases and simplified sharing.


Contents
========

.. toctree::
   :maxdepth: 2
   
   installation
   start
   guide/dockerfiles
   guide/context


Status
======
Docker-Map is being used for small-scale deployment scenarios in test and production. It should currently considered
beta, due to pending new features, generalizations, and unit tests.


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. _docker-py: https://github.com/docker/docker-py
.. _Docker-Fabric: https://github.com/merll/docker-fabric
.. _GitHub: https://github.com/merll/docker-map
