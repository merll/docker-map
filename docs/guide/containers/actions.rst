.. _container_actions:

Container actions
=================
This section explains what actions are implemented for managing containers in addition to the brief example in
:ref:`applying_maps`, as soon as :ref:`container_maps` are set up.

Basic container commands
------------------------
:class:`~dockermap.map.client.MappingDockerClient` provides as set of configurable commands, that transform the
container configurations and their current state into actions on the client, along with keyword arguments accepted by
`docker-py`. By default it supports the following methods:

* :meth:`~dockermap.map.client.MappingDockerClient.create` resolves all dependency containers to be created prior to
  the current one. First, `attached` volumes are created (see :ref:`attached-volumes`) of the dependency containers.
  Then the client creates dependency containers and the requested container. Existing containers are not re-created.
* Similarly, :meth:`~dockermap.map.client.MappingDockerClient.start` first launches dependency containers' `attached`
  volumes, then dependencies themselves, and finally the requested container. `Persistent` and `attached`,
  containers are not restarted if they have exited.
* :meth:`~dockermap.map.client.MappingDockerClient.restart` only restarts the selected container, not its dependencies.
* :meth:`~dockermap.map.client.MappingDockerClient.stop` stops the current container and containers that depend on it.
* :meth:`~dockermap.map.client.MappingDockerClient.remove` removes containers and their dependents, but does not
  remove attached volumes.
* :meth:`~dockermap.map.client.MappingDockerClient.startup`, along the dependency path,

  * removes containers with unrecoverable errors (currently codes ``-127`` and ``-1``, but may be extended as needed);
  * creates missing containers; if an attached volume is missing, the parent container is restarted;
  * and starts non-running containers (like `start`).
* :meth:`~dockermap.map.client.MappingDockerClient.shutdown` simply combines
  :meth:`~dockermap.map.client.MappingDockerClient.stop` and :meth:`~dockermap.map.client.MappingDockerClient.remove`.
* :meth:`~dockermap.map.client.MappingDockerClient.update` and
  :meth:`~dockermap.map.client.MappingDockerClient.run_script` are discussed in more detail below.

Updating containers
-------------------
:meth:`~dockermap.map.client.MappingDockerClient.update` checks along the dependency path for outdated containers or
container connections. In more detail, containers are removed, re-created, and restarted if any of the following
applies:

  * The image id from existing container is compared to the current id of the image as specified in the container
    configuration. If it does not match, the container is re-created based on the new image.
  * Linked containers, as declared on the map, are compared to the current container's runtime configuration. For
    legacy container links, if any container is missing or the linked alias mismatches, the dependent container is
    re-created and restarted. If used with configured container networks, only the network endpoint is re-created.
  * The virtual filesystem path of attached containers and other shared volumes is compared to dependent
    containers' paths. In case of a mismatch, the latter is updated.
  * The environment variables, command, and entrypoint of the container are compared to variables set in
    :attr:`~dockermap.map.config.container.ContainerConfiguration.create_options`. If any of them are missing or not matching,
    the container is considered outdated.
  * Exposed ports of the container are checked against :attr:`~dockermap.map.config.container.ContainerConfiguration.exposes`.
    If any ports are missing or configured differently, this also causes a container update.
  * The following container limits are checked against the host configuration of the currently-running container:

    * ``BlkioWeight``
    * ``CpuPeriod``
    * ``CpuQuota``
    * ``CpuShares``
    * ``CpusetCpus``
    * ``CpusetMems``
    * ``Memory``
    * ``MemoryReservation``
    * ``MemorySwap``
    * ``KernelMemory``

    If the Docker API supports it (version >= 1.22), changes will be applied to a running container (i.e. without the
    need to re-create the container). Due to a limitation in the Docker SDK for Python, existing limits can only be
    modified by not be removed (or set to zero). Where necessary, the container is reset unless
    ``skip_limit_reset=True`` is passed in as a keyword argument.

The keyword argument ``force_update`` takes a single name or list of container configuration names to force the update
on. This can be useful in cases where the need for re-creating a container cannot be detected automatically.

Post-start commands in :attr:`~dockermap.map.config.container.ContainerConfiguration.exec_commands` are checked if they can
be found on a running container, matching command line and user. If not, the configured command is executed, unless
:const:`dockermap.map.input.ExecPolicy.INITIAL` has been set for the command. By default
the entire command line is matched. For considering partial matches (i.e. if the command in the process overview gets
modified), you can set :attr:`~dockermap.map.state.update.main.UpdateStateGenerator.check_exec_commands` to
:const:`dockermap.map.input.CmdCheck.PARTIAL`. Setting it to :const:`dockermap.map.input.CmdCheck.NONE`
deactivates this check entirely.

Networks in :attr:`~dockermap.map.config.container.ContainerConfiguration.networks` are tested if they exist and if
the endpoint id matches. (Re-)connecting as necessary does not require a container restart.

For ensuring the integrity, all missing containers are created and started along the dependency path.
In order to see what defines a dependency, see :ref:`shared-volumes-containers` and :ref:`linked-containers`.

Additional keyword arguments to the ``start`` and ``create`` methods of the client are passed through; the order of
precedence towards the :class:`~dockermap.map.config.container.ContainerConfiguration` is further detailed in
:ref:`additional-options`. Example::

    map_client.start('web_server', restart_policy={'MaximumRetryCount': 0, 'Name': 'always'})

For limiting effects to particular :ref:`instances` of a container configuration, all these methods accept an
``instances`` argument, where one or multiple instance names can be specified. By implementing a custom subclass of
:class:`~dockermap.map.policy.base.BasePolicy`, the aforementioned behavior can be further adjusted to
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

Running scripts
---------------
The default client also implements a :meth:`~dockermap.map.client.MappingDockerClient.run_script` action. Its purpose is
to run a script or single command inside a container and automatically perform the necessary creation, start, and
cleanup, along with dependencies. Usage is slightly different from the other actions: Container configuration name and
map name are the first two arguments -- as usual -- but the third is only one optional instance name. Additionally, the
method supports the following optional arguments:

* ``script_path``: This may either be a file or a directory on the Docker host. If it points to a file, this will be
  assumed to be the script to run via the command. The parent directory will be available to the container, i.e. all
  other files in the same directory as the script. If ``entrypoint`` and ``command_format`` describe a self-contained
  action that does not require a script file, you can still point this to a path to include more files or write back
  results.
* ``entrypoint``: Entrypoint of the script runtime, e.g. ``/bin/bash``.
* ``command_format``: Just like ``command`` for a container, but any occurrence of a ``{script_path}`` variable is
  replaced with the path inside the container. This means that if ``script_path`` points to a script file
  ``/tmp/script.sh``, the command will be formatted with ``/tmp/script_run/test.sh`` (prefixed with the path
  specified in ``container_script_dir``). If it points to a directory, simply ``container_script_dir`` will be used
  in place of script path.
* ``wait_timeout``: Maximum time to wait before logging and returning the container output. By default the waiting
  time set up for the container :attr:`~dockermap.map.config.container.ContainerConfiguration.stop_timeout` or for the client
  :attr:`~dockermap.map.config.client.ClientConfiguration.timeout` is used.
* ``container_script_dir``: Path to run the script from inside the container. The default is ``/tmp/script_run``.
* ``timestamps`` and ``tail`` are simply passed through to the ``logs`` command of the `docker-py` client. They can be
  used to control the output of the script command.
* ``remove_existing_before``: Whether to remove containers with an identical name if they exist prior to running this
  command. By default, an existing container raises an exception. Setting this to ``True`` can be a simple way to
  recovering repeatable commands that have run into a timeout error.
* ``remove_created_after``: Whether to remove the container instance after a successful run (i.e. not running into a
  timeout), provided that it has been created by this command. This is the default behavior, so set this to ``False``
  if you intend to keep the stopped container around.

The :meth:`~dockermap.map.client.MappingDockerClient.run_script` method returns a dictionary with the client names
as keys, where the script was run. Values are nested dictionaries with keys ``log`` (the `stdout` of each container)
the ``exit_code`` that the container returned, and the temporary container id that had been created. In case the
``wait`` command timed out, the container logs and exit code are not available. In that case, the nested dictionary
contains the ``id`` of the container (which still exists) and a message in ``error``.

Containers that were created in the course of running the script are also stopped and removed again, unless waiting
timed out or ``remove_created_after`` was set to ``False``. If the container of the configuration exists prior to the
setup attempt and ``remove_existing_before`` is not set to ``True``, the script will not be run. In that case a
:class:`~dockermap.map.action.script.ScriptActionException` is thrown. In order to

Script examples
^^^^^^^^^^^^^^^
For running a bash script, set the executable bit on the file in your local path, and run it::

    map_client.run_script('test_container',
                          script_path='/tmp/test_path/test_script.sh',
                          entrypoint='/bin/bash',
                          command_format=['-c', '{script_path}'])

Assuming you have a `Redis` image and container with access to the socket in ``/var/run/redis/cache.sock``, you
can flush the database using::

    map_client.run_script('redis_client',
                          entrypoint='redis-cli',
                          command_format=['-s', '/var/run/redis/cache.sock', 'flushdb'])

Importing a `PostgreSQL` database to a server accessed via ``/var/run/postgresql/socket``, from a file stored in
``/tmp/db_import/my_db.backup``, can be performed with::

    map_client.run_script('postgres_client',
                          script_path='/tmp/db_import',
                          entrypoint='pg_restore',
                          command_format=['-h', '/var/run/postgresql/socket',
                                          '-d', 'my_db', '{script_path}/my_db.backup']


.. NOTE::
   In case files cannot be found by the script or command, check if ownership and access mode match the container
   user.


Options
-------
Aforementioned commands support a set of options, which are processed by different elements of the policy framework.
They can be modified in custom implementations, or changed by passing in keyword arguments.

* ``remove_existing_after`` (Actions: ``script``; Default: ``True``): Usually when the script action creates containers,
  it cleans up after. If you want to keep the containers, you can set this to ``False``.
* ``remove_existing_before`` (Actions: ``script``; Default: ``False``): Containers by the script action are created new,
  and if they exist it raises an error. Setting this to ``True`` removes any container that exists before creating new
  ones.
* ``remove_persistent`` (Actions: ``remove``, ``shutdown``; Default: ``True``): When removing containers, by default all
  configurations are considered. If this is set to ``False``, configurations marked as ``persistent`` are skipped.
* ``remove_attached`` (Actions: ``remove``, ``shutdown``; Default: ``False``): Attached containers serve for volume
  sharing on Docker versions prior to native volume support. By default they are not removed during ``remove`` and
  ``shutdown`` actions, but can optionally be included setting this to ``True`` .
* ``pull_all_images`` (Actions: ``pull``; Default: ``True``): The ``pull`` action attempts to download all images
  of the input container configurations, also updating existing ones with identical tags. If this is set to ``False``,
  only missing tags are pulled from the registry.
* ``pull_before_update`` (Actions: ``update``; Default: ``False``): Before an ``update`` operation, images of configured
  containers can optionally be pulled before detecting changes by setting this to ``True``.
* ``pull_insecure_registry`` (Actions: ``pull``, ``update``; Default: ``False``): Docker by default requires a
  registry to be published on a TLS encrypted connection (i.e. a HTTPS url), and the presented certificates to be
  trusted by the client (i.e. the Docker host). This is good practice and highly recommended; however, as Docker still
  offers the possibility to allow insecure connections, setting this flag to ``True`` makes use of it.
* ``prepare_local`` (Actions: ``create``, ``startup``, ``update``, ``script``; Default: ``True``):
* ``nonrecoverable_exit_codes`` (Actions: ``update``; Default: ``(-127, -1)``): Exit codes to assume that a container
  cannot be simply restarted, so that it has to be removed and re-created.
* ``force_update`` (Actions: ``update``; Default: ``None``): A string or list of container configurations that should
  be updated without checking. This can be used in case a change in the container configuration cannot be detected
  reliably.
* ``skip_limit_reset`` (Actions: ``update``; Default: ``False``): Due to a limitation of the current Docker API, limits
  of containers can be updated but not removed. This may lead to the need to re-create the container. If this is not
  desired, set this to ``True``.
* ``update_persistent`` (Actions: ``update``; Default: ``False``): Whether to remove containers where configurations
  are marked as ``persistent``.
* ``check_exec_commands`` (Actions: ``update``; Default: ``CmdCheck.FULL``): How to check the command of a running
  container against the configuration. By default performs to match the full command, but can be set to
  ``CmdCheck.PARTIAL`` for a partial lookup.
* ``restart_exec_commands`` (Actions: ``restart``; Default: ``False``): When a container is restarted and this is
  set to ``True``, all configured exec commands are also restarted.
