# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple


INITIAL_START_TIME = '0001-01-01T00:00:00Z'

STATE_ABSENT = 'absent'     # Does not exist.
STATE_PRESENT = 'present'   # Exists but is not running.
STATE_RUNNING = 'running'   # Exists and is running.

STATE_FLAG_INITIAL = 1                # Container is present but has never been started.
STATE_FLAG_RESTARTING = 1 << 1        # Container is not running, but in the process of restarting.
STATE_FLAG_NONRECOVERABLE = 1 << 10   # Container is stopped with an error that cannot be solved through restarting.
STATE_FLAG_FORCED_RESET = 1 << 11     # Container in any state should be reset.
STATE_FLAG_IMAGE_MISMATCH = 1 << 12   # Container does not correspond with configured image.
STATE_FLAG_MISSING_LINK = 1 << 13     # A configured linked container cannot be found.
STATE_FLAG_VOLUME_MISMATCH = 1 << 14  # Container is pointing to a different path than some of its configured volumes.
STATE_FLAG_NETWORK_DISCONNECT = 1 << 15  # Container is not connected to a network that it is configured for.
STATE_FLAG_MISC_MISMATCH = 1 << 20    # Container does otherwise not correspond with the configuration.

# TODO: Depends on Docker version
STATE_FLAG_NEEDS_RESET = (STATE_FLAG_NONRECOVERABLE | STATE_FLAG_FORCED_RESET | STATE_FLAG_IMAGE_MISMATCH |
                          STATE_FLAG_MISSING_LINK | STATE_FLAG_VOLUME_MISMATCH | STATE_FLAG_MISC_MISMATCH)

ConfigState = namedtuple('ConfigState', ['client_name', 'config_id', 'config_flags', 'base_state',
                                         'state_flags', 'extra_data'])
