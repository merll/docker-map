# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from six import iteritems

from ..action import (ACTION_CREATE, ACTION_RESTART, ACTION_STOP, ACTION_REMOVE, ACTION_KILL, ACTION_START,
                      ACTION_WAIT, UTIL_ACTION_PREPARE_CONTAINER)
from .base import DockerConfigMixin
from .attached import AttachedConfigMixin
from .cmd import ExecMixin
from . import AbstractRunner


KWARG_MAP = {
    'network_mode': 'net',
    'timeout': 'time',
    'ports': 'expose',
    'extra_hosts': 'add-host',
}


def _transform_kwargs(ka):
    for key, value in iteritems(ka):
        cmd_arg = KWARG_MAP.get(key, key.replace('_', '-'))
        if isinstance(value, list):
            for vi in value:
                yield '--{0}={1}'.format(cmd_arg, vi)
        elif isinstance(value, dict):
            for ki, vi in iteritems(value):
                yield '--{0}={1}:{2}'.format(cmd_arg, ki, vi)
        elif value is None:
            pass
        elif isinstance(value, bool):
            yield '--{0}={1}'.format(cmd_arg, 'true' if value else 'false')
        else:
            yield '--{0}={1}'.format(cmd_arg, value)


def _get_run_cmd(create_kwargs, host_config_kwargs):
    host_config_kwargs.pop('version', None)
    host_config_kwargs.pop('container', None)
    create_kwargs.update(host_config_kwargs)
    image = create_kwargs.pop('image')
    command = create_kwargs.pop('command', None)
    volumes = set(create_kwargs.pop('volumes', []))
    if create_kwargs.pop('network_disabled', False):
        create_kwargs['network_mode'] = 'none'

    def _get_vol_kwargs():
        for k, v in iteritems(create_kwargs.pop('binds', {})):
            v_path = v['bind']
            volumes.discard(v_path)
            if v['ro']:
                yield '{0}:{1}:{2}'.format(k, v_path, 'ro')
            else:
                yield '{0}:{1}'.format(k, v_path)
        for k in volumes:
            yield k

    def _get_ports_kwargs():
        for k, v in iteritems(create_kwargs.pop('port_bindings', {})):
            if isinstance(v, tuple):
                yield '{0}:{1}:{2}'.format(v[0], v[1], k)
            else:
                yield '{0}:{1}'.format(v, k)

    create_kwargs['volume'] = list(_get_vol_kwargs())
    create_kwargs['publish'] = list(_get_ports_kwargs())
    create_kwargs['link'] = [
        l[0] if l[0] == l[1] else '{0[0]}:{0[1]}'.format(l)
        for l in create_kwargs.pop('links', [])
    ]
    cmd_args = list(_transform_kwargs(create_kwargs))
    cmd_args.append(image)
    if command:
        if isinstance(command, list):
            cmd_args.extend(command)
        else:
            cmd_args.append(command)
    return 'docker run {0}'.format(' '.join(cmd_args))


def _get_cmd(cmd, cmd_kwargs):
    container = cmd_kwargs.pop('container')
    return 'docker {0} {1} {2}'.format(cmd, ' '.join(_transform_kwargs(cmd_kwargs)), container)


class DockerCommandOutputBaseMixin(object):
    attached_action_method_names = [
        (ACTION_CREATE, 'create'),
        (ACTION_START, 'start_attached'),
        (ACTION_RESTART, 'restart'),
        (ACTION_STOP, 'stop'),
        (ACTION_REMOVE, 'remove'),
        (ACTION_KILL, 'kill'),
        (ACTION_WAIT, 'wait'),
    ]
    instance_action_method_names = [
        (ACTION_CREATE, 'create'),
        (ACTION_START, 'start_instance'),
        (ACTION_RESTART, 'restart'),
        (ACTION_STOP, 'stop'),
        (ACTION_REMOVE, 'remove'),
        (ACTION_KILL, 'kill'),
        (ACTION_WAIT, 'wait'),
    ]

    def create(self, config, a_name, **kwargs):
        return None

    def start_attached(self, config, a_name, **kwargs):
        return _get_run_cmd(self.get_attached_create_kwargs(config, a_name, kwargs=kwargs),
                            self.get_attached_host_config_kwargs(config, a_name))

    def start_instance(self, config, c_name, **kwargs):
        return _get_run_cmd(self.get_create_kwargs(config, c_name, kwargs=kwargs),
                            self.get_host_config_kwargs(config, c_name))

    def restart(self, config, c_name, **kwargs):
        return _get_cmd('restart', self.get_restart_kwargs(config, c_name, kwargs=kwargs))

    def stop(self, config, c_name, **kwargs):
        return _get_cmd('stop', self.get_stop_kwargs(config, c_name, kwargs=kwargs))

    def remove(self, config, c_name, **kwargs):
        return _get_cmd('rm', self.get_remove_kwargs(config, c_name, kwargs=kwargs))

    def kill(self, config, c_name, **kwargs):
        return _get_cmd('kill', {'container': c_name})

    def wait(self, config, c_name, **kwargs):
        return _get_cmd('wait', self.get_wait_kwargs(config, c_name, kwargs=kwargs))


class DockerCommandAttachedPreparationMixin(AttachedConfigMixin):
    """
    Utility mixin for preparing attached containers with file system owners and permissions.
    """
    attached_action_method_names = [
        (UTIL_ACTION_PREPARE_CONTAINER, 'prepare_attached'),
    ]

    def prepare_attached(self, config, volume_container):
        """
        Runs a temporary container for preparing an attached volume for a container configuration.

        :param config: Configuration.
        :type config: ActionConfig
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode | str
        """
        apc_kwargs = self.get_attached_preparation_create_kwargs(config, volume_container)
        if not apc_kwargs:
            return None
        aph_kwargs = self.get_attached_preparation_host_config_kwargs(config, None, volume_container)
        apc_kwargs['command'] = "/bin/sh -c '{0}'".format(apc_kwargs['command'])
        apc_kwargs['rm'] = True
        return _get_run_cmd(apc_kwargs, aph_kwargs)


class DockerCommandExecMixin(ExecMixin):
    def exec_commands(self, config, c_name, run_cmds, **kwargs):
        """
        Runs a single command inside a container.

        :param config: Configuration.
        :type config: ActionConfig
        :param c_name: Container name.
        :type c_name: unicode | str
        :param run_cmds: Commands to run.
        :type run_cmds: list[dockermap.map.input.ExecCommand]
        """
        return ' && '.join(
            _get_cmd('exec', self.get_exec_create_kwargs(config, c_name, run_cmd.cmd, run_cmd.user))
            for run_cmd in run_cmds
        )


class DockerCommandOutputRunner(DockerCommandOutputBaseMixin, DockerConfigMixin, DockerCommandAttachedPreparationMixin,
                                DockerCommandExecMixin, AbstractRunner):
    """
    Returns command line strings for performing configured actions. Does not actually run anything on Docker.
    """
    pass
