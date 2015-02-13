.. _installation_and_configuration:

==============================
Installation and configuration
==============================

Installation
============
The current stable release, published on PyPI_, can be installed using the following command:

.. code-block:: bash

   pip install docker-map


For importing YAML configurations, you can install Docker-Map using

.. code-block:: bash

   pip install docker-map[yaml]


Dependencies
------------
The following libraries will be automatically installed from PyPI:

* docker-py (>=0.5.0)
* Optional: PyYAML (tested with 3.11) for YAML configuration import


Docker service
--------------
Docker needs to be installed on the target machine, and needs to be accessible either through a Unix socket or TCP/IP.
If you do not wish to expose a public network port from the host running Docker, consider using Docker-Fabric_.
Otherwise, for setting up a secure connection, refer to the `Docker documentation`_.


Imports
=======
The most essential classes are collected in the top-level :mod:`~dockermap.api` module for convenience. For example, you
can use::

    from dockermap.api import ContainerMap

rather than importing the class from the actual source module such as::

    from dockermap.map.container import ContainerMap


.. _PyPI: https://pypi.python.org/pypi/docker-map
.. _Docker-Fabric: https://pypi.python.org/pypi/docker-fabric
.. _`Docker documentation`: http://docs.docker.com/articles/https/
