.. _change_history:

Change History
==============

0.5.1
-----
* Adjusted volume path inspection to use ``Mounts`` on newer Docker API versions. Fixes issues with the update policy.

0.5.0
-----
* Implemented HostConfig during container creation, which is preferred over passing arguments during start since API
  v1.15. For older API versions, start keyword arguments will be used.
* Added configuration inheritance and abstract configurations.
* Changed log functions to be better fit Python logging.
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
