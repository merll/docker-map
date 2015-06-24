.. _change_history:

Change History
==============

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
* Various bugfixes.

0.3.0
-----
* Possibility to use 'lazy' values in various settings (e.g. port bindings, volume aliases, host volumes, and user).
* Consider read-only option for inherited volumes in ``uses`` property.
* Further update policy fixes.
* Python 3 compatibility fixes.

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
