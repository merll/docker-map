.. _change_history:

Change History
==============

0.2.0
-----
* Moved container handling logic to policy classes.
* Added ``startup``, ``shutdown``, and ``update`` actions, referring to variable policy implementations.
* Added ``persistent`` flag to container configurations to differentiate during cleanup processes.
* Added methods for merging container maps and configurations.
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
