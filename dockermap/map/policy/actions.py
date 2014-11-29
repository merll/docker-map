# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple


ACTION_DEPENDENCY_FLAG = 1 << 1
ACTION_ATTACHED_FLAG = 1 << 2

ACTION_CREATE = 10
ACTION_START = 20
ACTION_PREPARE = 30
ACTION_RESTART = 40
ACTION_STOP = 50
ACTION_REMOVE = 60

ContainerAction = namedtuple('ContainerAction', ('action', 'flags', 'map_name', 'container', 'kwargs'))
