# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from .actions import (ACTION_CREATE, ACTION_START, ACTION_PREPARE, ACTION_RESTART, ACTION_STOP, ACTION_REMOVE,
                      ACTION_ATTACHED_FLAG, ACTION_DEPENDENCY_FLAG, ContainerAction)

from .simple import SimplePolicy
from .resume import ResumeUpdatePolicy
