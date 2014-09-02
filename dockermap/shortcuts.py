# -*- coding: utf-8 -*-
from __future__ import unicode_literals

_P = ' -p'
_R = ' -R'
_F = ' -f'
_SYSTEM = ' --system'
_NO_LOGIN = ' --no-create-home --disabled-login --disabled-password'
_OUT_FILE = ' -o {0}'
_CHDIR = ' -C {0}'

_arg = lambda flag, is_set: flag if is_set else ''
_arg_format = lambda flag, arg: flag.format(arg) if arg else ''

rm = lambda path, recursive=False, force=False: 'rm{1}{2} {0}'.format(path, _arg(_R, recursive),  _arg(_F, force))
chown = lambda user_group, path, recursive=True: 'chown{2} {0} {1}'.format(get_user_group(user_group), path, _arg(_R, recursive))
chmod = lambda mode, path, recursive=True: 'chmod{2} {0} {1}'.format(mode, path, _arg(_R, recursive))

addgroup = lambda groupname, gid, system=False: 'addgroup{2} --gid {1} {0}'.format(groupname, gid, _arg(_SYSTEM, system))
adduser = lambda username, uid, system=False, no_login=True: 'adduser{2}{3} --uid {1} --gid {1} {0}'.format(username, uid, _arg(_SYSTEM, system), _arg(_NO_LOGIN, no_login))
assignuser = lambda username, groupnames: 'usermod -aG {1} {0}'.format(username, ','.join(groupnames))

curl = lambda url, filename=None: 'curl{1} {0}'.format(url, _arg_format(_OUT_FILE, filename))
wget = lambda url, filename=None: 'wget{1} {0}'.format(url, _arg_format(_OUT_FILE, filename))
targz = lambda filename, source: 'tar -czf {0} {1}'.format(filename, source)
untargz = lambda filename, target=None: 'tar{1} -xzf {0}'.format(filename, _arg_format(_CHDIR, target))


def get_user_group(user_group):
    """
    Formats a user and group in the format 'user:group', as needed for 'chown'. If user_group is a tuple, this is used
    for the fomatting. If a string or integer is given, it will be formatted as 'user:user'. Otherwise the input is
    returned - this method does not perform any more checks.

    :param user_group: User name, user id, user and group in format `user:group`, `user_id:group_id`, or tuple of (user, group).
    :type user_group: unicode, int, or tuple
    :return: Formatted string with in the format `user:group`.
    :rtype: unicode
    """
    if isinstance(user_group, tuple):
        return '{0}:{1}'.format(*user_group)
    elif isinstance(user_group, int) or not ':' in user_group:
        return '{0}:{0}'.format(user_group)
    else:
        return user_group


def addgroupuser(username, uid, groupnames=None, system=False, no_login=True, sudo=False):
    """
    Generates a unix command line for creating user and group with the same name, assigning the user to the group.
    Has the same effect as combining :func:`~addgroup`, :func:`~adduser`, and :func:`~assignuser`.

    :param username: User name to create.
    :type username: unicode
    :param uid: User id to use.
    :type uid: int
    :param groupnames: Iterable with additional group names to assign the user to.
    :type groupnames: iterable
    :param system: Create a system user and group. Default is `False`.
    :type system: bool
    :param no_login: Disallow login of this user and group, and skip creating the home directory. Default is `True`.
    :type no_login: bool
    :param sudo: Prepend `sudo` to the command. Default is `False`. When using Fabric, use its `sudo` command instead.
    :type sudo: bool
    :return: Unix shell command line.
    :rtype: unicode
    """
    group = addgroup(username, uid, system)
    user = adduser(username, uid, system, no_login)
    prefix = 'sudo ' if sudo else ''
    if groupnames:
        usermod = assignuser(username, groupnames)
        return '{0}{1} && {0}{2} && {0}{3}'.format(prefix, group, user, usermod)
    return '{0}{1} && {0}{2}'.format(prefix, group, user)


def mkdir(path, create_parent=True, check_if_exists=False):
    """
    Generates a unix command line for creating a directory.

    :param path: Directory path.
    :type path: unicode
    :param create_parent: Create parent directories, if necessary. Default is `True`.
    :type create_parent: bool
    :param check_if_exists: Prepend a check if the directory exists; in that case, the command is not run. Default is `False`.
    :type check_if_exists: bool
    :return: Unix shell command line.
    :rtype: unicode
    """
    cmd = 'mkdir{1} {0}'.format(path, _arg(_P, create_parent))
    if check_if_exists:
        return 'if [[ ! -d {0} ]]; then {1}; fi'.format(path, cmd)
    return cmd


def mkdir_chown(paths, user_group=None, permissions='ug=rwX,o=rX', create_parent=True, check_if_exists=False, recursive=False):
    """
    Generates a unix command line for creating a directory and assigning permissions to it. Shortcut to a combination of
    :func:`~mkdir`, :func:`~chown`, and :func:`~chmod`.

    Note that if `check_if_exists` has been set to `True`, and the directory is found, `mkdir` is not called, but
    `user_group` and `permissions` are still be applied.

    :param paths: Can be a single path string, or a list or tuple of path strings.
    :type paths: unicode or iterable
    :param: Optional owner of the directory. For notation, see :func:`~get_user_group`.
    :type user_group: unicode, int, or tuple
    :param permissions: Optional permission mode, in any notation accepted by the unix `chmod` command. Default is `ug=rwX,o=rX`.
    :type permissions: unicode
    :param create_parent: Parent directories are created if not present (`-p` argument to `mkdir`).
    :type create_parent: bool
    :param check_if_exists: Prior to creating the directory, checks if it already exists.
    :type check_if_exists: bool
    :param recursive: Apply permissions and owner change recursively.
    :type recursive: bool
    :return: Unix shell command line.
    :rtype: unicode
    """

    def _generate_str(path):
        mkdir_str = mkdir(path, create_parent, check_if_exists)
        chown_str = chown(user_group, path, recursive) if user_group else None
        chmod_str = chmod(permissions, path, recursive) if permissions else None
        return ' && '.join(n for n in (mkdir_str, chown_str, chmod_str) if n)

    if isinstance(paths, (tuple, list)):
        return '; '.join((_generate_str(path) for path in paths))
    return _generate_str(paths)
