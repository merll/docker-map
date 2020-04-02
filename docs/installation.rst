.. _installation_and_configuration:

==============================
Installation and configuration
==============================

Installation
============
The first version of the Docker API Python client was released as ``docker-py``. Version 2.x of the now so-called
Docker SDK for Python introduced some breaking changes and removed backwards compatibility with older Docker Remote API
versions. It was published with the ``pip`` package name ``docker``. Since Docker-Map currently supports *both*
versions which cannot be installed at the same time, none of them will be installed by default. You can either

* install one of ``docker`` or ``docker-py``,
* or use one of the extra-options below.

The current stable release, published on PyPI_, can be installed using the following command:

.. code-block:: bash

   pip install docker-map[docker]

This also installs the Docker SDK for Python 4.x. If you want to install the older implementation (version 1.x),
use the following instead:

.. code-block:: bash

   pip install docker-map[legacy]


For importing YAML configurations, you can install Docker-Map using

.. code-block:: bash

   pip install docker-map[yaml]


Upgrading
---------
If you were using an older version (< 1.0.0) of Docker-Map and want to migrate from ``docker-py`` (1.x) to the new
``docker`` (>2.x) library, uninstall the older one first, and then reinstall:

.. code-block:: bash

   pip uninstall docker-py
   pip install docker


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
