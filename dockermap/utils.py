# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os

from .functional import lazy_once


expand_path = lambda value: os.path.expanduser(os.path.expandvars(value))
expand_path_lazy = lambda value: lazy_once(expand_path, value)
