# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple

from ...map import Flags, SimpleEnum

INITIAL_START_TIME = '0001-01-01T00:00:00Z'


class State(SimpleEnum):
    ABSENT = 'absent'     # Does not exist.
    PRESENT = 'present'   # Exists but is not running.
    RUNNING = 'running'   # Exists and is running.


class StateFlags(Flags):
    INITIAL = 1                # Container is present but has never been started.
    RESTARTING = 1 << 1        # Container is not running, but in the process of restarting.
    PERSISTENT = 1 << 5        # Container is configured as persistent.
    NONRECOVERABLE = 1 << 10   # Container is stopped with an error that cannot be solved through restarting.
    IMAGE_MISMATCH = 1 << 12   # Container does not correspond with configured image.
    MISSING_LINK = 1 << 13     # A configured linked container cannot be found.
    VOLUME_MISMATCH = 1 << 14  # Container is pointing to a different path than some of its configured volumes.
    EXEC_COMMANDS = 1 << 15    # Container is missing at least one exec command.
    NETWORK_DISCONNECTED = 1 << 20  # Container is not connected to a network that it is configured for.
    NETWORK_LEFT = 1 << 21     # Container is connected to a network that it is not configured for.
    NETWORK_MISMATCH = 1 << 22  # Container has different configured connection parameters than the current link.
    MISC_MISMATCH = 1 << 30    # Item does otherwise not correspond with the configuration.
    FORCED_RESET = 1 << 31     # Item in any state should be reset.

    NEEDS_RESET = (NONRECOVERABLE | FORCED_RESET | IMAGE_MISMATCH | MISSING_LINK | VOLUME_MISMATCH | MISC_MISMATCH)


ConfigState = namedtuple('ConfigState', ['client_name', 'config_id', 'config_flags', 'base_state',
                                         'state_flags', 'extra_data'])
