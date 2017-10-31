.. _change_history:

Change History
==============
0.8.0rc1
--------
* Added checks on configured ip addresses and link-local ips. Additional general improvements to container network
  endpoint check against configuration.
* Added checks on volume driver and driver options.
* After an unsuccessful stop attempt, added another wait period so that the container has time to process the
  ``SIGKILL`` signal issued by Docker.
* Process a single ``MapConfigId`` as valid input.
* Moved ``CmdCheck`` flags to :mod:`~dockermap.map.input` module.

0.8.0b5
-------
* The :meth:`~dockermap.map.client.MappingDockerClient.pull_images` action also pulls present images by default (i.e.
  updates them from the registry). This was optional before, and can be prevented by passing ``pull_all_images=False``,
  only pulling missing image tags.
* Internal cleanup of converting input into configuration ids.

0.8.0b4
-------
* Included main process id in state data, so that implementations can detect a container restart more easily.
* Handling deprecation of the ``force`` argument when tagging images in newer Docker releases. The tag is added
  automatically depending on the detected API version.
* Fixed update check of container network mode referring to another container.
* Additional minor bugfix from previous prereleases.

0.8.0b3
-------
* Added :attr:`~dockermap.map.config.main.ContainerMap.volumes`: Where the Docker host supports it, volumes can now be
  configured with additional properties such as driver and options. The original workaround of Docker containers sharing
  anonymous volumes no longer applies in this case.
* The default path of volumes in :attr:`~dockermap.map.config.container.ContainerConfiguration.attaches` volumes can now
  be defined, by using a dictionary or list of tuples. They no longer have to (but still can) be set in
  :attr:`~dockermap.map.config.main.ContainerMap.volumes`.
* Where the Docker host supports named volumes, container-side paths of
  :attr:`~dockermap.map.config.container.ContainerConfiguration.uses` items can be overridden, provided that they are
  referring to attached volumes created through another container.
* Removed ``clients`` property from :class:`~dockermap.map.config.container.ContainerConfiguration`. It caused too much
  complexity in responding to supported client features. In addition, it was likely to break dependency paths.
  :attr:`~dockermap.map.config.main.ContainerMap.clients` is however still available.

0.8.0b2
-------
* :class:`~dockermap.map.client.MappingDockerClient` now wraps all exceptions so that partial results, i.e. actions that
  already have been performed on clients. It raises a :class:`~dockermap.map.exceptions.ActionRunnerException`, which
  provides information about the client and action performed, partial results through
  :meth:`~dockermap.exceptions.PartialResultsMixin.results`, but also the possibility to re-trigger the original
  traceback using :meth:`~dockermap.exceptions.SourceExceptionMixin.reraise`.
* Similarly, direct calls to the utility client :class:`~dockermap.client.base.DockerClientWrapper`, such as
  :meth:`~dockermap.client.docker_util.DockerUtilityMixin.cleanup_containers` now return a
  :class:`~dockermap.exceptions.PartialResultsError`.
* Added :meth:`~dockermap.map.client.MappingDockerClient.signal` method to client.
* Images have been integrated into the dependency resolution. Images of a container and all of its dependencies can
  now be pulled with the new command :meth:`~dockermap.map.client.MappingDockerClient.pull_images`.
* Authentication information for the Docker registry can now be added to
  :attr:`dockermap.map.config.client.ClientConfiguration.auth_configs` and are considered during login and image pull
  actions.
* Added a built-in group ``__all__``, that applies to all containers or even all configured maps on
  :class:`~dockermap.map.client.MappingDockerClient`.
* Several adaptions which makes it easier for programs and libraries using the API to evaluate changes.
* More fixes to image dependency check, so that
  :meth:`~dockermap.client.docker_util.DockerUtilityMixin.cleanup_images` now works reliably. Removals can also be
  forced where applicable.
* Implemented CLI, missing from 0.8.0b1.
* Various bugfixes from 0.8.0b1.

0.8.0b1
-------
* Added :attr:`~dockermap.map.config.main.ContainerMap.groups`: Generally an action (e.g. startup of containers) can
  now be run at once on multiple items. In order to make input easier, groups can be added to a map that refers to
  multiple configurations. Dependencies that multiple items have in common will only be followed once.
* Added forced update: Not all differences between the container configuration and an existing instance can be detected
  automatically. A parameter ``force_update`` can now trigger an update of particular containers.
* Added :attr:`~dockermap.map.config.main.ContainerMap.networks`: Docker networks can now be configured
  on a map. Referring to them in the property :attr:`~dockermap.map.config.container.ContainerConfiguration.networks`
  from one or multiple container configurations will create them automatically. The former ``network`` setting has been
  renamed to :attr:`~dockermap.map.config.container.ContainerConfiguration.network_mode` for disambiguation.

0.7.6
-----
* More sensible solution of `Issue #15 <https://github.com/merll/docker-map/issues/15>`_, not changing user-defined
  link aliases. Doing so could cause name resolution issues.

0.7.5
-----
* Minor fixes for compatibility with newer Docker hosts.
* Followup fixes from `Issue #15 <https://github.com/merll/docker-map/issues/15>`_.

0.7.4
-----
* Fixed case where ``exec_create`` does not return anything, as when commands are started immediately (e.g. the CLI,
  `Issue #17 <https://github.com/merll/docker-map/issues/17>`_).
* Improved accuracy of comparing the container command from the configuration with the container inspection info.
* Added parser for CLI ``top`` command, as needed for inspecting exec commands.

0.7.3
-----
* Fixed command line generator for case where ``cmd`` is used as a keyword argument
  (`Issue #16 <https://github.com/merll/docker-map/issues/16>`_).

0.7.2
-----
* Fixed recursive dependency resolution order.
* Setting an alias name is always optional for container links, even if ``ContainerLinks`` tuple is used directly.

0.7.1
-----
* Added ``version`` method to command line generator.
* Internal refactoring: Moved configuration elements to individual modules. If you get any import errors from this
  update, please check if you are using convenience imports such as ``from dockermap.api import ContainerMap`` instead
  of the modules where the classes are implemented.
* Fixed ``ContainerMap.containers`` attribute access to work as documented.

  .. note::
    The default iteration behavior has also changed. Similar to ``ContainerMap.host`` and ``ContainerMap.volumes``, it
    generates items. Before iteration was returning keys, as usual for dictionaries.

* Fixes for use of alternative client implementations (e.g. CLI,
  `Issue #12 <https://github.com/merll/docker-map/issues/12>`_).
* Fixed ``link`` argument for command line generator (`Issue #13 <https://github.com/merll/docker-map/issues/13>`_).
* Added replacement for invalid characters in generated host names
  (`Issue #15 <https://github.com/merll/docker-map/issues/15>`_).

0.7.0
-----
* Refactoring of policy framework. The monolithic client action functions have been divided into separate
  modules for improving maintainability and testing. This also makes it easier to add more functionality.
  A few minor issues with updating containers and executing commands were resolved during this change.
* Added an experimental command line generator.

0.6.6
-----
* Added evaluation of ``.dockerignore`` files.
* Several bugfixes from `0.6.6b1`.

0.6.6b1
-------
* Added arguments to set additional image tags after build.
* Added ``default_tag`` property to container maps.
* Minor refactoring. Possibly breaks compatibility in custom policy implementations:

  * ``dockermap.map.policy.cache.CachedImages.reset_latest`` has been renamed to
    :meth:`~dockermap.map.policy.cache.CachedImages.reset_updated`.
  * :meth:`~dockermap.map.policy.cache.CachedImages.ensure_image` argument ``pull_latest`` has been renamed to
    ``pull``.
  * ``dockermap.map.policy.update.ContainerUpdateMixin.pull_latest`` has been renamed to
    :attr:`~dockermap.map.policy.update.ContainerUpdateMixin.pull_before_update`.
  * ``dockermap.map.policy.base.BasePolicy.iname`` has been renamed to
    :meth:`~dockermap.map.policy.base.BasePolicy.image_name` and changed order of arguments for allowing defaults.

0.6.5
-----
* Better support for IPv6 addresses. Added ``ipv6`` flag to port bindings and ``interfaces_ipv6`` property to client
  configuration.
* Command elements are converted into strings so that Dockerfiles with a numeric command line element do not raise
  errors.

0.6.4
-----
* Fixed exception on stopping a container configuration when the container does not exist.

0.6.3
-----
* Improved fixed behavior when merging container maps and embedded container configurations. Can also be used for
  creating copies.
* Added ``stop_timeout`` argument to ``remove_all_containers``.
* Fixed transfer of configuration variables into client instance.

0.6.2
-----
* Added ``stop_signal`` for customizing the signal that is used for shutting down or restarting containers.
* Minor changes in docs and log messages.
* Fixed image cache update with multiple tags.
* Bugfix in Dockerfile module.

0.6.1
-----
* Many more Python 3 fixes (`PR #10 <https://github.com/merll/docker-map/pull/10>`_).
* Cleaned up logging; only using default levels.
* Port bindings are passed as lists to the API, allowing container ports to be published to multiple host
  ports and interfaces.

0.6.0
-----
* Added ``exec_commands`` to start additional commands (e.g. scripts) along with the container.
* Container links are now passed as lists to the API, so that the same container can be linked with multiple
  aliases.
* Various compatibility fixes with Python 3 (`PR #9 <https://github.com/merll/docker-map/pull/9>`_).
* Bugfixes on container restart and configuration merge.

0.5.3
-----
* Bugfixes for network mode and volume check of inherited configurations.
* Fixed deprecation warnings from ``docker-py``.
* Added option to prepare attached volumes with local commands instead of temporary containers, for clients that
  support it.

0.5.2
-----
* Added network modes and their dependencies. Attached volumes are no longer enabled for networking.
* Added per-container stop timeout. Also applies to restart.

0.5.1
-----
* Adjusted volume path inspection to use ``Mounts`` on newer Docker API versions. Fixes issues with the update policy.

0.5.0
-----
* Implemented HostConfig during container creation, which is preferred over passing arguments during start since API
  v1.15. For older API versions, start keyword arguments will be used.
* Added configuration inheritance and abstract configurations.
* Changed log functions to better fit Python logging.
* Minor fixes in merge functions.
* Bug fix in tag / repository partitioning (`PR #7 <https://github.com/merll/docker-map/pull/7>`_).

0.4.1
-----
* Added automated container start, log, and removal for scripts or single commands.
* Added separate exception type for map integrity check failures.
* Aliases for host volumes are now optional.
* Minor bugfixes in late value resolution, container cleanup, and input conversion.

0.4.0
-----
* Added check for changes in environment, command, and network settings in update policy.
* Added optional pull before new container creation.
* Revised dependency resolution for avoiding duplicate actions and detecting circular dependencies more reliably.
* Fix for handling missing container names in cleanup method.
* Allow for merging empty dictionary keys.

0.3.3
-----
* Fix for missing container names and tags.
* Exclude default client name from host name.

0.3.2
-----
* Fixed error handling in build (issue #6).
* New ``command_workdir`` for setting the working directory in DockerFiles.
* Enhanced file adding functions in DockerFile to return build context paths.
* Fixed volume consistency check in update policy.
* Additional minor updates.

0.3.1
-----
* Extended late value resolution to custom types.
* Various bugfixes (e.g. `PR #5 <https://github.com/merll/docker-map/pull/5>`_).

0.3.0
-----
* Possibility to use 'lazy' values in various settings (e.g. port bindings, volume aliases, host volumes, and user).
* Consider read-only option for inherited volumes in ``uses`` property.
* Further update policy fixes.
* Python 3 compatibility fixes (`PR #4 <https://github.com/merll/docker-map/pull/4>`_).

0.2.2
-----
* Added convenience imports in ``api`` module.

0.2.1
-----
* Added host and domain name setting.
* Improved update requirement detection.
* Fixed restart policy.

0.2.0
-----
* Moved container handling logic to policy classes.
* Better support for multiple maps and multiple clients.
* Added ``startup``, ``shutdown``, and ``update`` actions, referring to variable policy implementations.
* Added ``persistent`` flag to container configurations to differentiate during cleanup processes.
* Added methods for merging container maps and configurations.
* It is no longer required to use the wrapped client ``DockerClientWrapper``.
* More flexible logging.

0.1.4
-----
* Minor fix in ``DockerFile`` creation.

0.1.3
-----
* Only setup fix, no functional changes.

0.1.2
-----
* Various bugfixes related to repository prefix, shortcuts, users.

0.1.1
-----
* Added YAML import.
* Added default host root path and repository prefix.
* Added Docker registry actions to wrapper.
* Fixed issues related to starting containers.

0.1.0
-----
Initial release.
