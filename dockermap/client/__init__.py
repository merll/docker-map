# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from distutils.version import StrictVersion


DEPRECATED_FORCE_TAG_VERSION = StrictVersion(str('1.24'))
DEPRECATED_COPY_VERSION = StrictVersion(str('1.20'))


def use_force_tag(api_version):
    return StrictVersion(str(api_version)) < DEPRECATED_FORCE_TAG_VERSION


def use_get_archive(api_version):
    return StrictVersion(str(api_version)) >= DEPRECATED_COPY_VERSION
