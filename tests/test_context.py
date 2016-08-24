# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import unittest
from tarfile import TarInfo

import os

from dockermap.build.context import get_filter_func, preprocess_matches

SAMPLE_IGNORE_SIMPLE = r"""
.*
dir1
dir2/**/a
dir3/*/testfile
dir3/a\\b*
"""

SAMPLE_IGNORE_WITH_NEGATIVES = r"""
.*
!.include
!test/.root
dir3/**
!dir3
*/*/testfile
!dir3/*/testfile
dir3/drop/*
"""


TEST_MATCH_FILES_SIMPLE = [
    'abc',
    'dir4',
    'abc/cde',
    'dir2',
    'dir2/sub/b',
    'dir2/sub/sub/b',
    'dir3/sub/c',
]

TEST_EXCLUDE_FILES_SIMPLE = [
    '.git',
    '.dockerignore',
    'dir1',
    'dir2/sub/a',
    'dir3/a\\bc',
]

TEST_MATCH_FILES_MIXED = [
    '.include',
    'dir2',
    'dir3',
    'dir3/keep/testfile',
    'test/.root',
]

TEST_EXCLUDE_FILES_MIXED = [
    '.git',
    'dir3/drop/testfile',
    'dir3/drop/this',
    'dir3/unrelated/file',
]


class TestDockerIgnorePatterns(unittest.TestCase):
    def setUp(self):
        self.prefix1 = prefix1 = '/root/folder1/'
        self.prefix2 = prefix2 = '/root/folder2/'
        simple_matches = list(preprocess_matches(SAMPLE_IGNORE_SIMPLE.splitlines()))
        self.simple_filter = get_filter_func(simple_matches, prefix1)
        mixed_matches = list(preprocess_matches(SAMPLE_IGNORE_WITH_NEGATIVES.splitlines()))
        self.mixed_filter = get_filter_func(mixed_matches, prefix2)

    def test_simple_matches(self):
        filter_func = self.simple_filter
        prefix = self.prefix1.lstrip('/')
        for fn in TEST_MATCH_FILES_SIMPLE:
            self.assertIsNotNone(filter_func(TarInfo(os.path.join(prefix, fn))),
                                 "Unexpectedly excluded {0}".format(fn))

    def test_simple_exclusions(self):
        filter_func = self.simple_filter
        prefix = self.prefix1.lstrip('/')
        for fn in TEST_EXCLUDE_FILES_SIMPLE:
            self.assertIsNone(filter_func(TarInfo(os.path.join(prefix, fn))),
                              "Unexpectedly kept {0}".format(fn))

    def test_mixed_matches(self):
        filter_func = self.mixed_filter
        prefix = self.prefix2.lstrip('/')
        for fn in TEST_MATCH_FILES_MIXED:
            self.assertIsNotNone(filter_func(TarInfo(os.path.join(prefix, fn))),
                                 "Unexpectedly excluded {0}".format(fn))

    def test_mixed_exclusions(self):
        filter_func = self.mixed_filter
        prefix = self.prefix2.lstrip('/')
        for fn in TEST_EXCLUDE_FILES_MIXED:
            self.assertIsNone(filter_func(TarInfo(os.path.join(prefix, fn))),
                              "Unexpectedly kept {0}".format(fn))
