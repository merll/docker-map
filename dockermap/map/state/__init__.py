# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple


INITIAL_START_TIME = '0001-01-01T00:00:00Z'

STATE_ABSENT = 'absent'     # Does not exist.
STATE_PRESENT = 'present'   # Exists but is not running.
STATE_RUNNING = 'running'   # Exists and is running.

STATE_FLAG_INITIAL = 1               # Container is present but has never been started.
STATE_FLAG_RESTARTING = 1 << 1       # Container is not running, but in the process of restarting.
STATE_FLAG_NONRECOVERABLE = 1 << 10  # Container is stopped with an error that cannot be solved through restarting.
STATE_FLAG_OUTDATED = 1 << 11        # Container in any base state does not correspond with current config.

ContainerConfigStates = namedtuple('ContainerConfigState', ['client', 'map', 'config', 'flags', 'instances',
                                                            'attached'])
ContainerInstanceState = namedtuple('ContainerInstanceState', ['instance', 'base_state', 'flags', 'extra_data'])
