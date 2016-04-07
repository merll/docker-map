# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six


def str_arg(arg):
    return six.text_type(arg).replace(' ', '\\ ')


def _gen_kwargs(kwargs):
    for k, v in six.iteritems(kwargs):
        if isinstance(v, tuple):
            if v[0]:
                yield ' '.join(map(str_arg, v[1:]))
        elif not isinstance(v, bool) and v is not None:
            yield '{0} {1}'.format(k.replace('_', '-'), str_arg(v))
        elif v:
            yield k.replace('_', '-')


def _format_cmd(cmd, *args, **kwargs):
    arg_str = ' '.join(map(str_arg, args))
    kwarg_str = ' '.join(_gen_kwargs(kwargs))
    if kwarg_str:
        return '{0} {1} {2}'.format(cmd, kwarg_str, arg_str)
    return '{0} {1}'.format(cmd, arg_str)


_NO_LOGIN = '--disabled-login'
_NO_CREATE_HOME = '--no-create-home'
_NO_PASSWORD = '--disabled-password'

rm = lambda path, recursive=False, force=False: _format_cmd('rm', path, _R=bool(recursive), _f=bool(force))
chown = lambda user_group, path, recursive=True: _format_cmd('chown', get_user_group(user_group), path,
                                                             _R=bool(recursive))
chmod = lambda mode, path, recursive=True: _format_cmd('chmod', mode, path, _R=bool(recursive))

addgroup = lambda groupname, gid, system=False: _format_cmd('groupadd', groupname, __system=bool(system), __gid=gid)
assignuser = lambda username, groupnames: _format_cmd('usermod', username, _aG=','.join(groupnames))

curl = lambda url, filename=None: _format_cmd('curl', url, _o=filename)
wget = lambda url, filename=None: _format_cmd('wget', url, _o=filename)
targz = lambda filename, source: _format_cmd('tar', filename, source, _czf=True)
untargz = lambda filename, target=None: _format_cmd('tar', filename, _xzf=True, _C=target)


def adduser(username, uid=None, system=False, no_login=True, no_password=False, group=False, gecos=None, **kwargs):
    """
    Formats an ``adduser`` command.

    :param username: User name.
    :type username: unicode | str
    :param uid: Optional user id to use.
    :type uid: long | int
    :param system: Create a system user account.
    :type system: bool
    :param no_login: Disable the login for this user. Not compatible with CentOS. Implies setting '--no-create-home',
      and ``no_password``.
    :type no_login: bool
    :param no_password: Disable the password for this user. Not compatible with CentOS.
    :type no_password: bool
    :param group: Create a group along with the user. Not compatible with CentOS.
    :type group: bool
    :param gecos: Set GECOS information in order to suppress an interactive prompt. On CentOS, use ``__comment``
      instead.
    :type gecos: unicode | str
    :param kwargs: Additional keyword arguments which are converted to the command line.
    :return: A formatted ``adduser`` command with arguments.
    :rtype: unicode | str
    """
    return _format_cmd('adduser', username, __system=bool(system), __uid=uid, __group=bool(group), __gid=uid,
                       no_login=(no_login, _NO_CREATE_HOME, _NO_LOGIN),
                       __disabled_password=no_login or bool(no_password),
                       __gecos=gecos, **kwargs)


def get_user_group(user_group):
    """
    Formats a user and group in the format ``user:group``, as needed for `chown`. If user_group is a tuple, this is used
    for the fomatting. If a string or integer is given, it will be formatted as ``user:user``. Otherwise the input is
    returned - this method does not perform any more checks.

    :param user_group: User name, user id, user and group in format ``user:group``, ``user_id:group_id``, or tuple of
      ``(user, group)``.
    :type user_group: unicode | str | int | tuple
    :return: Formatted string with in the format ``user:group``.
    :rtype: unicode | str
    """
    if isinstance(user_group, tuple):
        return '{0}:{1}'.format(*user_group)
    elif isinstance(user_group, six.integer_types) or ':' not in user_group:
        return '{0}:{0}'.format(user_group)
    return user_group


def addgroupuser(username, uid, groupnames=None, system=False, no_login=True, no_password=False, gecos=None, sudo=False,
                 **kwargs):
    """
    Generates a unix command line for creating user and group with the same name, assigning the user to the group.
    Has the same effect as combining :func:`~addgroup`, :func:`~adduser`, and :func:`~assignuser`.

    :param username: User name to create.
    :type username: unicode | str
    :param uid: User id to use.
    :type uid: int
    :param groupnames: Iterable with additional group names to assign the user to.
    :type groupnames: iterable
    :param system: Create a system user and group. Default is ``False``.
    :type system: bool
    :param no_login: Disallow login of this user and group, and skip creating the home directory. Default is ``True``.
    :type no_login: bool
    :param no_password: Do not set a password for the new user.
    :type: no_password: bool
    :param gecos: Provide GECOS info and suppress prompt.
    :type gecos: unicode | str
    :param sudo: Prepend `sudo` to the command. Default is ``False``. When using Fabric, use its `sudo` command instead.
    :type sudo: bool
    :param kwargs: Additional keyword arguments for command line arguments.
    :return: Unix shell command line.
    :rtype: unicode | str
    """
    group = addgroup(username, uid, system)
    user = adduser(username, uid, system, no_login, no_password, False, gecos, **kwargs)
    prefix = 'sudo ' if sudo else ''
    if groupnames:
        usermod = assignuser(username, groupnames)
        return '{0}{1} && {0}{2} && {0}{3}'.format(prefix, group, user, usermod)
    return '{0}{1} && {0}{2}'.format(prefix, group, user)


def mkdir(path, create_parent=True, check_if_exists=False):
    """
    Generates a unix command line for creating a directory.

    :param path: Directory path.
    :type path: unicode | str
    :param create_parent: Create parent directories, if necessary. Default is ``True``.
    :type create_parent: bool
    :param check_if_exists: Prepend a check if the directory exists; in that case, the command is not run.
      Default is ``False``.
    :type check_if_exists: bool
    :return: Unix shell command line.
    :rtype: unicode | str
    """
    cmd = _format_cmd('mkdir', path, _p=create_parent)
    if check_if_exists:
        return 'if [[ ! -d {0} ]]; then {1}; fi'.format(path, cmd)
    return cmd


def mkdir_chown(paths, user_group=None, permissions='ug=rwX,o=rX', create_parent=True, check_if_exists=False, recursive=False):
    """
    Generates a unix command line for creating a directory and assigning permissions to it. Shortcut to a combination of
    :func:`~mkdir`, :func:`~chown`, and :func:`~chmod`.

    Note that if `check_if_exists` has been set to ``True``, and the directory is found, `mkdir` is not called, but
    `user_group` and `permissions` are still be applied.

    :param paths: Can be a single path string, or a list or tuple of path strings.
    :type paths: unicode | str | iterable
    :param: Optional owner of the directory. For notation, see :func:`~get_user_group`.
    :type user_group: unicode | str | int | tuple
    :param permissions: Optional permission mode, in any notation accepted by the unix `chmod` command.
      Default is ``ug=rwX,o=rX``.
    :type permissions: unicode | str
    :param create_parent: Parent directories are created if not present (`-p` argument to `mkdir`).
    :type create_parent: bool
    :param check_if_exists: Prior to creating the directory, checks if it already exists.
    :type check_if_exists: bool
    :param recursive: Apply permissions and owner change recursively.
    :type recursive: bool
    :return: Unix shell command line.
    :rtype: unicode | str
    """

    def _generate_str(path):
        mkdir_str = mkdir(path, create_parent, check_if_exists)
        chown_str = chown(user_group, path, recursive) if user_group else None
        chmod_str = chmod(permissions, path, recursive) if permissions else None
        return ' && '.join(n for n in (mkdir_str, chown_str, chmod_str) if n)

    if isinstance(paths, (tuple, list)):
        return '; '.join((_generate_str(path) for path in paths))
    return _generate_str(paths)
