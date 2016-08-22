# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
from itertools import groupby
from operator import itemgetter

import re
import time

from six import iteritems, text_type

from docker.errors import NotFound


KWARG_MAP = {
    'timeout': 'time',
    'extra_hosts': 'add-host',
    'nocache': 'no-cache',
    'volumes': 'volume',
}
NONE_TAG = '<none>'
_arg_format = '--{0}={1}'.format
_mapping_format = '--{0}={1}:{2}'.format
_format_tag = '{0[0]}:{0[1]}'.format
_get_image_id = itemgetter(2)


def _quoted_arg_format(key, value):
    return '--{0}="{1}"'.format(key, text_type(value).replace('"', '\\"'))


CONTAINER_FORMAT_ARG = _quoted_arg_format('format', '{{.ID}}||{{.Image}}||{{.CreatedAt}}||{{.Status}}||{{.Names}}||'
                                                    '{{.Command}}||{{.Ports}}')


def _summarize_tags(image_id, image_lines):
    first_line = next(image_lines)
    image_tags = [_format_tag(first_line)] if first_line[0] != NONE_TAG else []
    image_tags.extend(_format_tag(image) for image in image_lines if image[0] != NONE_TAG)
    return {
        'Id': image_id,
        'RepoTags': image_tags or NONE_TAG,
        'ParentId': '',
        'Created': 0,
        'VirtualSize': 0,
        'Size': 0,
    }


CREATED_AT_PATTERN = re.compile(r'(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}) \+\d{4} \w+')
PRIVATE_PORT_PATTERN = re.compile('(?P<PrivatePort>\d+(-\d+)?)\/(?P<Type>\w+)')
PUBLIC_PORT_PATTERN = re.compile(r'(?P<IP>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(?P<PublicPort>\d+(-\d+)?)->'
                                 r'(?P<PrivatePort>\d+(-\d+)?)\/(?P<Type>\w+)')


def _port_info(ports):
    for port in ports.split(', '):
        public_match = PUBLIC_PORT_PATTERN.match(port)
        if public_match:
            yield public_match.groupdict()
        else:
            private_match = PRIVATE_PORT_PATTERN.match(port)
            if private_match:
                yield private_match.groupdict()


def _container_info(line):
    items = line.split('||')
    return {
        'Id': items[0],
        'Image': items[1],
        'Created': time.mktime(map(int, CREATED_AT_PATTERN.match(items[2]).groups()) + [0, 0, 0]),
        'Status': items[3],
        'Names': ['/{0}'.format(name) for name in items[4].split(',')],
        'Command': items[5].strip('"'),
        'Ports': list(_port_info(items[6])),
    }


def _first_key_value(d, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return k, v
    return None, None


def _transform_kwargs(ka):
    for key, value in iteritems(ka):
        cmd_arg = KWARG_MAP.get(key, key.replace('_', '-'))
        if isinstance(value, list):
            for vi in value:
                yield _quoted_arg_format(cmd_arg, vi)
        elif isinstance(value, dict):
            for ki, vi in iteritems(value):
                yield _mapping_format(cmd_arg, ki, vi)
        elif value is None:
            pass
        elif isinstance(value, bool):
            yield _arg_format(cmd_arg, 'true' if value else 'false')
        else:
            yield _quoted_arg_format(cmd_arg, value)


def _transform_create_kwargs(ka):
    network = ka.pop('network_mode', None)
    network_disabled = ka.pop('network_disabled', False)
    environment = ka.pop('environment', None)
    binds = ka.pop('binds', None)
    volumes = ka.pop('volumes', None) if binds else None
    expose = ka.pop('ports', None)
    port_bindings = ka.pop('port_bindings', None)

    for arg in _transform_kwargs(ka):
        yield arg

    if environment:
        if isinstance(environment, list):
            for vi in environment:
                yield _quoted_arg_format('env', vi)
        elif isinstance(environment, dict):
            for ki, vi in iteritems(environment):
                yield _quoted_arg_format('env', '{0}={1}'.format(ki, vi))

    if network_disabled:
        yield _arg_format('net', 'none')
    elif network:
        yield _arg_format('net', network)

    if volumes:
        bind_keys = {}
        for b in binds:
            b_key = b.split(':')[1]
            bind_keys[b_key] = b
        for v in volumes:
            v_bind = bind_keys.get(v)
            if v_bind:
                yield _quoted_arg_format('volume', v_bind)
            else:
                yield _quoted_arg_format('volume', v)

    if expose and port_bindings:
        for e in expose:
            yield _arg_format('expose', e)
            if isinstance(e, tuple):
                port, proto = e
            else:
                port, proto = e, None
            if proto:
                pkey = '{0}/{1}'.format(port, proto)
                pbind = port_bindings.get(pkey)
            else:
                pkey, pbind = _first_key_value(port_bindings, port, text_type(port), '{0}/tcp')
            if pbind:
                for pbi in pbind:
                    if isinstance(pbi, tuple):
                        b_ip, b_port = pbi
                        yield _arg_format('publish', '{0}:{1}:{2}'.format(b_ip, b_port, pkey))
                    else:
                        yield _arg_format('publish', '{0}:{1}'.format(pbi, pkey))


def parse_containers_output(out):
    return [
        _container_info(line) for line in out.splitlines() or ()
    ]


def parse_inspect_output(out):
    parsed = json.loads(out, encoding='utf-8')
    if parsed:
        return parsed[0]
    raise NotFound("Container not found.", None)


def parse_images_output(out):
    lines = out.splitlines()
    line_iter = iter(lines)
    next(line_iter)  # Skip header
    split_lines = (line.split() for line in line_iter)
    return [
        _summarize_tags(image_id, image_lines)
        for image_id, image_lines in groupby(sorted(split_lines, key=_get_image_id), key=_get_image_id)
    ]


class DockerCommandLineOutput(object):
    cmd_map = {
        'create_container': 'create',
        'containers': 'ps',
        'exec_create': 'exec',
        'exec_start': None,
        'inspect_container': 'inspect',
        'remove_container': 'rm',
        'remove_image': 'rmi',
    }

    def __init__(self, cmd_prefix=None, default_bin='docker', cmd_args=None):
        super(DockerCommandLineOutput, self).__init__()
        if cmd_prefix:
            cmd = '{0} {1}'.format(cmd_prefix, default_bin)
        else:
            cmd = default_bin
        if cmd_args:
            self._cmd = '{0} {1}'.format(cmd, ' '.join(cmd_args))
        else:
            self._cmd = cmd

    def get_cmd(self, cmd, *args, **kwargs):
        cli_cmd = self.cmd_map.get(cmd, cmd)
        if not cli_cmd:
            return None
        cmd_prefix = None
        cmd_args = [cli_cmd]
        if cli_cmd == 'create':
            p_arg = kwargs.pop('image')
            exec_cmd = kwargs.pop('command', None)
            cmd_args.extend(_transform_create_kwargs(kwargs))
        elif cli_cmd == 'exec':
            p_arg = kwargs.pop('container')
            cmd_args.append('--detach')
            exec_cmd = kwargs.pop('cmd')
            cmd_args.extend(_transform_kwargs(kwargs))
        else:
            if cli_cmd in ('images', 'ps'):
                cmd_args.append('--no-trunc')
                if cli_cmd == 'ps':
                    cmd_args.append(CONTAINER_FORMAT_ARG)
                p_arg = None
            else:
                if cli_cmd == 'wait':
                    timeout = kwargs.pop('timeout', None)
                    if timeout:
                        cmd_prefix = 'timeout -s INT {0} '.format(timeout)
                p_arg = kwargs.pop('container', None)
            exec_cmd = None
            cmd_args.extend(_transform_kwargs(kwargs))
        if p_arg:
            cmd_args.append(p_arg)
        if exec_cmd:
            if isinstance(exec_cmd, list):
                cmd_args.extend(exec_cmd)
            else:
                cmd_args.append(exec_cmd)
        cmd_args.extend(args)
        return '{0}{1} {2}'.format(cmd_prefix or '', self._cmd, ' '.join(cmd_args))
