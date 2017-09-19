# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
from itertools import groupby, islice
from operator import itemgetter

import re
import time

from six import iteritems, text_type
from six.moves import map

from docker.errors import NotFound

from ..utils import format_image_tag


KWARG_MAP = {
    'timeout': 'time',
    'extra_hosts': 'add-host',
    'nocache': 'no-cache',
    'volumes': 'volume',
    'options': 'opt',
    'ipv4_address': 'ip',
    'ipv6_address': 'ip6',
    'links': 'link',
    'aliases': 'alias',
}
NONE_TAG = '<none>'
_arg_format = '--{0}={1}'.format
_mapping_format = '--{0}={1}:{2}'.format
_get_image_id = itemgetter(2)


def _quoted_arg_format(key, value):
    return '--{0}="{1}"'.format(key, text_type(value).replace('"', '\\"'))


_CONTAINER_FIELDS = ['ID', 'Image', 'CreatedAt', 'Status', 'Names', 'Command', 'Ports']
CONTAINER_FORMAT_ARG = _quoted_arg_format('format', '||'.join('{{{{.{0}}}}}'.format(f) for f in _CONTAINER_FIELDS))
VERSION_FORMAT_ARG = _quoted_arg_format('format', '{{json .}}')


def _summarize_tags(image_id, image_lines):
    first_line = next(image_lines)
    image_tags = [format_image_tag(first_line)] if first_line[0] != NONE_TAG else []
    image_tags.extend(format_image_tag(image) for image in image_lines if image[0] != NONE_TAG)
    return {
        'Id': image_id,
        'RepoTags': image_tags or NONE_TAG,
        'ParentId': '',
        'Created': 0,
        'VirtualSize': 0,
        'Size': 0,
    }


CREATED_AT_PATTERN = re.compile(r'(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}) [+-]\d{4} \w+')
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
        'Created': time.mktime(list(map(int, CREATED_AT_PATTERN.match(items[2]).groups())) + [0, 0, 0]),
        'Status': items[3],
        'Names': ['/{0}'.format(name) for name in items[4].split(',')],
        'Command': items[5].strip('"'),
        'Ports': list(_port_info(items[6])),
    }


def _network_info(line):
    items = line.split()
    return {
        'Id': items[0],
        'Name': items[1],
        'Driver': items[2],
        'Scope': items[3],
    }


def _volume_info(line):
    items = line.split()
    return {
        'Driver': items[0],
        'Name': items[1],
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
    network_config = ka.pop('networking_config', None)
    environment = ka.pop('environment', None)
    binds = ka.pop('binds', None)
    volumes = ka.pop('volumes', None) if binds else None
    expose = ka.pop('ports', None)
    port_bindings = ka.pop('port_bindings', None)
    links = ka.pop('links', None)

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
    elif network_config:
        ep_config = network_config['EndpointsConfig']
        network_name = ep_config.keys()[0]
        nc = ep_config[network_name]
        yield _arg_format('net', network_name)
        for a in nc.get('Aliases') or ():
            yield _arg_format('network-alias', a)
        for l in nc.get('Links') or ():
            yield _arg_format(l)
        ipam = nc.get('IPAMConfig')
        if ipam:
            ip4 = ipam.get('IPv4Address')
            if ip4:
                yield _arg_format('ip', ip4)
            ip6 = ipam.get('IPv6Address')
            if ip6:
                yield _arg_format('ip6', ip6)
            for l in ipam.get('LinkLocalIPs') or ():
                yield _arg_format('link-local-ip', l)

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

    if links:
        for l in links:
            yield _mapping_format('link', *l)


def parse_containers_output(out):
    """
    Parses the output of the Docker CLI 'docker ps --format="{{ID}}||{{Image}}||..."' and returns it in the format
    similar to the Docker API.

    :param out: CLI output.
    :type out: unicode | str
    :return: Parsed result.
    :rtype: list[dict]
    """
    return [
        _container_info(line) for line in out.splitlines() or ()
    ]


def parse_networks_output(out):
    """
    Parses the output of the Docker CLI 'docker network ls' and returns it in the format similar to the Docker API.

    :param out: CLI output.
    :type out: unicode | str
    :return: Parsed result.
    :rtype: list[dict]
    """
    if not out:
        return []
    line_iter = islice(out.splitlines(), 1, None)  # Skip header
    return list(map(_network_info, line_iter))


def parse_volumes_output(out):
    """
    Parses the output of the Docker CLI 'docker volume ls' and returns it in the format similar to the Docker API.

    :param out: CLI output.
    :type out: unicode | str
    :return: Parsed result.
    :rtype: list[dict]
    """
    if not out:
        return []
    line_iter = islice(out.splitlines(), 1, None)  # Skip header
    return list(map(_volume_info, line_iter))


def parse_inspect_output(out, item_type):
    """
    Parses the output of the Docker CLI 'docker inspect <container>' or 'docker network inspect <network>'. Essentially
    just returns the parsed JSON string, like the Docker API does.

    :param out: CLI output.
    :type out: unicode | str
    :param item_type: Type of the item that has been inspected (e.g. 'container').
    :type item_type: unicode | str
    :return: Parsed result.
    :rtype: dict
    """
    parsed = json.loads(out, encoding='utf-8')
    if parsed:
        return parsed[0]
    raise NotFound("{0} not found.".format(item_type.title()), None)


def parse_images_output(out):
    """
    Parses the output of the Docker CLI 'docker images'. Note this is currently incomplete and only returns the ids and
    tags of images, as the Docker CLI heavily modifies the output for human readability. The parent image id is also
    not available on the CLI, so a full API compatibility is not possible.

    :param out: CLI output.
    :type out: unicode | str
    :return: Parsed result.
    :rtype: list[dict]
    """
    line_iter = islice(out.splitlines(), 1, None)  # Skip header
    split_lines = (line.split() for line in line_iter)
    return [
        _summarize_tags(image_id, image_lines)
        for image_id, image_lines in groupby(sorted(split_lines, key=_get_image_id), key=_get_image_id)
    ]


def parse_version_output(out):
    """
    Parses the output of 'docker version --format="{{json .}}"'. Essentially just returns the parsed JSON string,
    like the Docker API does. Fields are slightly different however.

    :param out: CLI output.
    :type out: unicode | str
    :return: Parsed result.
    :rtype: dict
    """
    parsed = json.loads(out, encoding='utf-8')
    if parsed:
        return parsed.get('Client', {})
    return {}


def parse_top_output(out):
    """
    Parses the output of the Docker CLI 'docker top <container>'. Note that if 'ps' output columns are modified and
    'args' (for the command) is anywhere but in the last column, this will not parse correctly. However, the Docker API
    produces wrong output in this case as well.
    Returns a dictionary with entries 'Titles' and 'Processes' just like the Docker API would.

    :param out: CLI output.
    :type out: unicode | str
    :return: Parsed result.
    :rtype: dict
    """
    lines = out.splitlines()
    line_iter = iter(lines)
    header_line = next(line_iter)
    titles = header_line.split()
    max_split = len(titles) - 1
    return {
        'Titles': titles,
        'Processes': [line.split(None, max_split) for line in line_iter],
    }


def _extend_or_append(cmd_args, exec_cmd):
    if exec_cmd:
        if isinstance(exec_cmd, list):
            cmd_args.extend(exec_cmd)
        else:
            cmd_args.append(exec_cmd)


class DockerCommandLineOutput(object):
    cmd_map = {
        'create_container': 'create',
        'containers': 'ps',
        'exec_create': 'exec',
        'exec_start': None,
        'inspect_container': 'inspect',
        'remove_container': 'rm',
        'remove_image': 'rmi',
        'create_network': 'network create',
        'networks': 'network ls',
        'inspect_network': 'network inspect',
        'remove_network': 'network rm',
        'create_volume': 'volume create',
        'volumes': 'volume ls',
        'inspect_volume': 'volume inspect',
        'remove_volume': 'volume rm',
        'connect_container_to_network': 'network connect',
        'disconnect_container_from_network': 'network disconnect',
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

    def get_cmd(self, c_cmd, *args, **kwargs):
        cli_cmd = self.cmd_map.get(c_cmd, c_cmd)
        if not cli_cmd:
            return None
        cmd_prefix = None
        cmd_args = [cli_cmd]
        if cli_cmd == 'create':
            p_args = [kwargs.pop('image')]
            _extend_or_append(p_args, kwargs.pop('command', None))
            cmd_args.extend(_transform_create_kwargs(kwargs))
        elif cli_cmd == 'exec':
            p_args = [kwargs.pop('container')]
            _extend_or_append(p_args, kwargs.pop('cmd'))
            cmd_args.append('--detach')
            cmd_args.extend(_transform_kwargs(kwargs))
        elif cli_cmd in ('network create', 'volume create', 'volume rm'):
            p_args = [kwargs.pop('name')]
            cmd_args.extend(_transform_kwargs(kwargs))
        elif cli_cmd.startswith('network') and (cli_cmd.endswith('connect') or cli_cmd.endswith('rm')):
            p_args = [kwargs.pop('net_id')]
            if cli_cmd.endswith('connect'):
                p_args.append(kwargs.pop('container'))
            cmd_args.extend(_transform_kwargs(kwargs))
        else:
            if cli_cmd in ('images', 'ps', 'network ls'):
                cmd_args.append('--no-trunc')
                if cli_cmd == 'ps':
                    cmd_args.append(CONTAINER_FORMAT_ARG)
                p_args = None
            elif cli_cmd == 'version':
                cmd_args.append(VERSION_FORMAT_ARG)
                p_args = None
            else:
                if cli_cmd == 'wait':
                    timeout = kwargs.pop('timeout', None)
                    if timeout:
                        cmd_prefix = 'timeout -s INT {0} '.format(timeout)
                container_arg = kwargs.pop('container', None)
                if container_arg:
                    p_args = [container_arg]
                else:
                    p_args = None
            cmd_args.extend(_transform_kwargs(kwargs))
        if p_args:
            cmd_args.extend(p_args)
        cmd_args.extend(args)
        return '{0}{1} {2}'.format(cmd_prefix or '', self._cmd, ' '.join(cmd_args))
