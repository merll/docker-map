# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from .map import SimpleEnum


class CmdArgMappings(SimpleEnum):
    DEBIAN = 'debian'
    BUSYBOX = 'busybox'
    CENTOS = 'centos'


CMD_ARG_MAPPING = {
    CmdArgMappings.DEBIAN: {
        'no_login': '--disabled-login',
        'no_create_home': '--no-create-home',
        'no_password': '--disabled-password',
        'gecos': '--gecos',
        'system_user': '--system',
    },
    CmdArgMappings.CENTOS: {
        'no_login': '--disabled-login',
        'no_create_home': '--no-create-home',
        'no_password': None,
        'gecos': '--comment',
        'system_user': '--system',
    },
    CmdArgMappings.BUSYBOX: {
        'no_login': '-s /bin/false',
        'no_create_home': '-H',
        'no_password': '-D',
        'gecos': '-g',
        'system_user': '-S',
    },
}


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


rm = lambda path, recursive=False, force=False: _format_cmd('rm', path, _R=bool(recursive), _f=bool(force))
chown = lambda user_group, path, recursive=True: _format_cmd('chown', get_user_group(user_group), path,
                                                             _R=bool(recursive))
chmod = lambda mode, path, recursive=True: _format_cmd('chmod', mode, path, _R=bool(recursive))

curl = lambda url, filename=None: _format_cmd('curl', url, _o=filename)
wget = lambda url, filename=None: _format_cmd('wget', url, _o=filename)


def _replace_mapped_cmd_args(cmd_kwargs, arg_mapping):
    mapped_cmds = CMD_ARG_MAPPING.get(arg_mapping)
    if mapped_cmds:
        for arg_key, cmd_arg in six.iteritems(mapped_cmds):
            arg_val = cmd_kwargs.pop(arg_key, None)
            if arg_val is not None and arg_val is not False:
                if cmd_arg is None:
                    raise ValueError("Argument {0} is not supported on {1}.".format(arg_key, arg_mapping))
                cmd_kwargs[cmd_arg] = arg_val


def adduser(username, uid=None, system=False, no_login=True, no_password=False, gecos=None,
            arg_mapping=CmdArgMappings.DEBIAN, **kwargs):
    """
    Formats an ``adduser`` command.

    :param username: User name.
    :type username: unicode | str
    :param uid: Optional user id to use.
    :type uid: long | int
    :param system: Create a system user account.
    :type system: bool
    :param no_login: Disable the login for this user. Not compatible with CentOS. Implies setting '--no-create-home'.
    :type no_login: bool
    :param no_password: Disable the password for this user. Not compatible with CentOS.
    :type no_password: bool
    :param gecos: Set GECOS information in order to suppress an interactive prompt.
    :type gecos: unicode | str
    :param kwargs: Additional keyword arguments which are converted to the command line.
    :return: A formatted ``adduser`` command with arguments.
    :rtype: unicode | str
    """
    cmd_kwargs = dict(
        system_user=bool(system), no_password=bool(no_password), gecos=gecos, _u=uid
    )
    if arg_mapping == CmdArgMappings.BUSYBOX:
        cmd_kwargs['_G'] = username
    else:
        cmd_kwargs['_g'] = uid
    if no_login:
        cmd_kwargs.update(
            no_create_home=True,
            no_login=True,
        )
        if arg_mapping != CmdArgMappings.CENTOS:
            cmd_kwargs['no_password'] = True
    cmd_kwargs.update(kwargs)
    _replace_mapped_cmd_args(cmd_kwargs, arg_mapping)
    return _format_cmd('adduser', username, **cmd_kwargs)


def addgroup(groupname, gid=None, system=False, arg_mapping=CmdArgMappings.DEBIAN, **kwargs):
    cmd_kwargs = dict(
        system_user=bool(system), _g=gid
    )
    cmd_kwargs.update(kwargs)
    _replace_mapped_cmd_args(cmd_kwargs, arg_mapping)
    return _format_cmd('addgroup', groupname, **cmd_kwargs)


def assignuser(username, groupnames, arg_mapping=CmdArgMappings.DEBIAN, return_list=False, **kwargs):
    if arg_mapping == CmdArgMappings.BUSYBOX:
        cmds = [
            _format_cmd('adduser', username, group_name, **kwargs)
            for group_name in groupnames
        ]
    else:
        cmds = [_format_cmd('usermod', username, _aG=','.join(groupnames), **kwargs)]
    if return_list:
        return cmds
    return ' && '.join(cmds)


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


def addgroupuser(username, uid, groupnames=None, system=False, no_login=True, no_password=False, gecos=None,
                 arg_mapping=CmdArgMappings.DEBIAN, return_list=False, **kwargs):
    """
    Generates a unix command line for creating user and group with the same name, assigning the user to the group.
    Has the same effect as combining :func:`~addgroup`, :func:`~adduser`, and :func:`~assignuser`.

    :param username: User name to create.
    :type username: unicode | str
    :param uid: User id to use.
    :type uid: int
    :param groupnames: Iterable with additional group names to assign the user to.
    :type groupnames: collections.Iterable[unicode | str]
    :param system: Create a system user and group. Default is ``False``.
    :type system: bool
    :param no_login: Disallow login of this user and group, and skip creating the home directory. Default is ``True``.
    :type no_login: bool
    :param no_password: Do not set a password for the new user.
    :type: no_password: bool
    :param gecos: Provide GECOS info and suppress prompt.
    :type gecos: unicode | str
    :param kwargs: Additional keyword arguments for command line arguments.
    :return: Unix shell command line.
    :rtype: unicode | str
    """
    cmds = [addgroup(username, gid=uid, system=system, arg_mapping=arg_mapping)]
    adduser_kwargs = dict(uid=uid, system=system, no_login=no_login, no_password=no_password, gecos=gecos,
                          arg_mapping=arg_mapping, **kwargs)
    if groupnames:
        if arg_mapping == CmdArgMappings.BUSYBOX:
            usermod = assignuser(username, groupnames, arg_mapping=arg_mapping, return_list=True)
        else:
            adduser_kwargs.update(_G=','.join(groupnames))
            usermod = None
    else:
        usermod = None
    cmds.append(adduser(username, **adduser_kwargs))
    if usermod:
        cmds.extend(usermod)
    if return_list:
        return cmds
    return ' && '.join(cmds)


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
    :type paths: unicode | str | tuple[unicode | str] | list[unicode | str]
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


def tar(filename, source, **kwargs):
    return _format_cmd('tar', source, _cf=filename, **kwargs)


def untar(filename, target=None, **kwargs):
    return _format_cmd('tar', _xf=filename, _C=target, **kwargs)


def targz(filename, source, **kwargs):
    return tar(filename, source, _z=True, **kwargs)


def untargz(filename, target=None, **kwargs):
    return untar(filename, target=target, _z=True, **kwargs)
