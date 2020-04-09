# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import shlex
import unittest

from dockermap.shortcuts import (str_arg, get_user_group, rm, chown, chmod, curl, wget, tar, untar, targz, untargz,
                                 mkdir, mkdir_chown, addgroup, CmdArgMappings, assignuser, adduser, addgroupuser)


def _split_cmd_args(cmd):
    current = None
    split_items = shlex.split(cmd)
    if split_items:
        first = split_items.pop(0)
    else:
        first = None
    if split_items and not split_items[-1][0] == '-':
        last = split_items.pop()
    else:
        last = None
    misc_args = []
    for ci in split_items:
        if ci.startswith('-') or not current:
            if current:
                misc_args.append(current)
            current = ci
        else:
            misc_args.append('{0} {1}'.format(current, shlex.quote(ci)))
            current = None
    if current:
        misc_args.append(current)
    return first, last, misc_args


class ShortcutTest(unittest.TestCase):
    def assertContainsAllArgs(self, cmd, start=None, end=None, *seq):
        first, last, misc_args = _split_cmd_args(cmd)
        if start:
            self.assertEqual(start, first)
        if end:
            self.assertEqual(end, last)
        self.assertSetEqual(set(seq), set(misc_args))

    def test_str_arg(self):
        self.assertEqual(r"'abc def'", str_arg("abc def"))
        self.assertEqual("123", str_arg(123))
        self.assertEqual(r"' '", str_arg(" "))
        self.assertEqual(r"'  '", str_arg("  "))

    def test_get_user_group(self):
        self.assertEqual('user:group', get_user_group(('user', 'group')))
        self.assertEqual('1000:1001', get_user_group((1000, 1001)))
        self.assertEqual('user:user', get_user_group('user'))
        self.assertEqual('1000:1000', get_user_group(1000))
        self.assertEqual('user:group', get_user_group('user:group'))

    def test_rm(self):
        self.assertEqual('rm path/to/rm', rm('path/to/rm'))
        self.assertEqual('rm -R path/to/rm', rm('path/to/rm', recursive=True))
        self.assertEqual('rm -f path/to/rm', rm('path/to/rm', force=True))
        self.assertEqual('rm -R -f path/to/rm', rm('path/to/rm', recursive=1, force=1))

    def test_chown(self):
        self.assertEqual('chown user:group path/to/chown', chown('user:group', 'path/to/chown', recursive=False))
        self.assertEqual('chown user:group path/to/chown', chown('user:group', 'path/to/chown', recursive=0))
        self.assertEqual('chown -R user:group path/to/chown', chown('user:group', 'path/to/chown'))
        self.assertEqual('chown -R user:group path/to/chown', chown('user:group', 'path/to/chown', recursive=True))
        self.assertEqual('chown -R user:group path/to/chown', chown('user:group', 'path/to/chown', recursive='true'))

    def test_chmod(self):
        self.assertEqual('chmod -R 0700 path/to/chmod', chmod('0700', 'path/to/chmod'))
        self.assertEqual('chmod u+x path/to/chmod', chmod('u+x', 'path/to/chmod', recursive=False))

    def test_curl(self):
        self.assertEqual('curl https://example.com', curl('https://example.com'))
        self.assertEqual('curl -o out-filename https://example.com', curl('https://example.com', 'out-filename'))

    def test_wget(self):
        self.assertEqual('wget https://example.com', wget('https://example.com'))
        self.assertEqual('wget -o out-filename https://example.com', wget('https://example.com', 'out-filename'))

    def test_adduser(self):
        self.assertContainsAllArgs(
            adduser('user1'),
            'adduser', 'user1', '--no-create-home', '--disabled-login', '--disabled-password', "--gecos ''")
        self.assertContainsAllArgs(
            adduser('user1', arg_mapping=CmdArgMappings.CENTOS),
            'adduser', 'user1', '--no-create-home', '-s /sbin/nologin')
        self.assertContainsAllArgs(
            adduser('user1', gecos="User 1", no_login=False, arg_mapping=CmdArgMappings.CENTOS),
            'adduser', 'user1', "--comment 'User 1'")
        self.assertContainsAllArgs(
            adduser('user1', arg_mapping=CmdArgMappings.BUSYBOX),
            'adduser', 'user1', '-D', '-H', '-s /sbin/nologin')
        self.assertEqual("adduser --gecos '' user1",
                         adduser('user1', no_login=False))
        self.assertContainsAllArgs(
            adduser('user1', no_login=False, no_password=True),
            'adduser', 'user1', "--gecos ''", '--disabled-password')
        self.assertRaises(ValueError, adduser,
                          'user1', no_login=False, no_password=True, arg_mapping=CmdArgMappings.CENTOS)
        self.assertContainsAllArgs(
            adduser('user1', no_login=False, no_password=True, arg_mapping=CmdArgMappings.BUSYBOX),
            'adduser', 'user1', '-D')

    def test_addgroup(self):
        self.assertEqual('addgroup groupname', addgroup('groupname'))
        self.assertEqual('addgroup -g 2000 groupname', addgroup('groupname', gid=2000))
        self.assertContainsAllArgs(
            addgroup('groupname', gid=2000, system='x', arg_mapping=CmdArgMappings.DEBIAN),
            'addgroup', 'groupname', '-g 2000', '--system')
        self.assertContainsAllArgs(
            addgroup('groupname', gid=2000, system=True, arg_mapping=CmdArgMappings.CENTOS),
            'addgroup', 'groupname', '-g 2000', '--system')
        self.assertContainsAllArgs(
            addgroup('groupname', gid=2000, system=True, arg_mapping=CmdArgMappings.BUSYBOX),
            'addgroup', 'groupname', '-g 2000', '-S')

    def test_assignuser(self):
        self.assertEqual('usermod -aG group1 username', assignuser('username', ['group1']))
        self.assertEqual('usermod -aG group1,group2 username', assignuser('username', ['group1', 'group2']))
        self.assertEqual('usermod -aG group1,group2 username',
                         assignuser('username', ['group1', 'group2'], arg_mapping=CmdArgMappings.CENTOS))
        self.assertEqual('adduser username group1 && adduser username group2',
                         assignuser('username', ['group1', 'group2'], arg_mapping=CmdArgMappings.BUSYBOX))

    def test_addgroupuser(self):
        cmds_debian = addgroupuser('user1', ['a', 'b'], return_list=True)
        self.assertEqual(1, len(cmds_debian))
        self.assertContainsAllArgs(
            cmds_debian[0],
            'adduser', 'user1', '-G a,b', '--no-create-home', '--disabled-login', '--disabled-password', "--gecos ''")
        cmds_centos = addgroupuser('user1', ['a', 'b'], arg_mapping=CmdArgMappings.CENTOS, return_list=True)
        self.assertEqual(1, len(cmds_centos))
        self.assertContainsAllArgs(
            cmds_centos[0],
            'adduser', 'user1', '-G a,b', '--no-create-home', '-s /sbin/nologin')
        cmds_busybox = addgroupuser('user1', ['a', 'b'], arg_mapping=CmdArgMappings.BUSYBOX, return_list=True)
        self.assertEqual(3, len(cmds_busybox))
        self.assertContainsAllArgs(
            cmds_busybox[0],
            'adduser', 'user1', '-H', '-D', '-s /sbin/nologin')
        self.assertEqual(cmds_busybox[1], 'adduser user1 a')
        self.assertEqual(cmds_busybox[2], 'adduser user1 b')

    def test_mkdir(self):
        self.assertEqual('mkdir -p path/to/mk', mkdir('path/to/mk'))
        self.assertEqual('mkdir path/to/mk', mkdir('path/to/mk', create_parent=False))
        self.assertEqual('if [[ ! -d path/to/mk ]]; then mkdir -p path/to/mk; fi',
                         mkdir('path/to/mk', check_if_exists=True))
        self.assertEqual('if [[ ! -d path/to/mk ]]; then mkdir path/to/mk; fi',
                         mkdir('path/to/mk', create_parent=False, check_if_exists=True))

    def test_mkdir_chown(self):
        self.assertEqual('mkdir -p path/a && chown user:user path/a && chmod ug=rwX,o=rX path/a',
                         mkdir_chown('path/a', 'user'))
        self.assertEqual('mkdir path/a && chown 1000:1001 path/a && chmod ug=rwX,o=rX path/a',
                         mkdir_chown('path/a', (1000, 1001), create_parent=False))
        self.assertEqual('mkdir -p path/a && chown -R user:group path/a && chmod -R ug=rwX,o=rX path/a',
                         mkdir_chown('path/a', 'user:group', recursive=True))
        self.assertEqual('mkdir -p path/a && chmod 0700 path/a',
                         mkdir_chown('path/a', None, permissions='0700'))
        self.assertEqual('mkdir -p path/a && chown -R user:group path/a; '
                         'mkdir -p path/b && chown -R user:group path/b',
                         mkdir_chown(('path/a', 'path/b'), 'user:group', permissions=None, recursive=True))
        self.assertEqual('mkdir -p path/a && chown user:group path/a && chmod ug=rwX,o=rX path/a; '
                         'mkdir -p path/b && chown user:group path/b && chmod ug=rwX,o=rX path/b',
                         mkdir_chown(['path/a', 'path/b'], 'user:group'))
        self.assertEqual([['mkdir -p path/a', 'chown user:group path/a', 'chmod ug=rwX,o=rX path/a'],
                          ['mkdir -p path/b', 'chown user:group path/b', 'chmod ug=rwX,o=rX path/b']],
                         mkdir_chown(['path/a', 'path/b'], 'user:group', return_list=True))

    def test_tar(self):
        self.assertEqual('tar -cf archive.tar src/path', tar('archive.tar', 'src/path'))
        self.assertContainsAllArgs(tar('archive.tar', 'src/path', _v=True),
                                   'tar', 'src/path', '-cf archive.tar', '-v')

    def test_untar(self):
        self.assertContainsAllArgs(untar('archive.tar', 'src/path'),
                                   'tar', 'src/path', '-xf archive.tar', '-C')
        self.assertContainsAllArgs(untar('archive.tar', 'src/path', _v=True),
                                   'tar', None, '-xf archive.tar', '-C src/path', '-v')

    def test_targz(self):
        self.assertContainsAllArgs(targz('archive.tar', 'src/path'),
                                   'tar', 'src/path', '-cf archive.tar', '-z')
        self.assertContainsAllArgs(targz('archive.tar', 'src/path', _v=True),
                                   'tar', 'src/path', '-cf archive.tar', '-z', '-v')

    def test_untargz(self):
        self.assertContainsAllArgs(untargz('archive.tar', 'src/path'),
                                   'tar', None, '-xf archive.tar', '-C src/path', '-z')
        self.assertContainsAllArgs(untargz('archive.tar', 'src/path', _v=True),
                                   'tar', None, '-xf archive.tar', '-C src/path', '-z', '-v')
