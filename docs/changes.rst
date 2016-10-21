.. _change_history:

Change History
==============
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
  * :meth:``dockermap.map.policy.cache.CachedImages.ensure_image`` argument ``pull_latest`` has been renamed to
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
