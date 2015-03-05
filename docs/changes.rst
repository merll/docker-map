.. _change_history:

Change History
==============

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
