# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

import os
import six
import yaml
from .container import ContainerMap
from ..utils import expand_path


def expand_path_node(loader, node):
    """
    Expands paths on a YAML document node. If it is a sequence node (list) items on the first level are expanded. For
    a mapping node (dict), values are expanded.

    :param loader: YAML loader.
    :type loader: yaml.loader.SafeLoader
    :param node: Document node.
    :type node: ScalarNode, MappingNode, or SequenceNode
    :return: unicode, list, or dict
    """
    if isinstance(node, yaml.nodes.ScalarNode):
        val = loader.construct_scalar(node)
        return expand_path(val)
    elif isinstance(node, yaml.nodes.MappingNode):
        val = loader.construct_mapping(node)
        for d_key, d_val in six.iteritems(val):
            val[d_key] = expand_path(d_val)
        return val
    elif isinstance(node, yaml.nodes.SequenceNode):
        val = loader.construct_sequence(node)
        if isinstance(val, list):
            return [expand_path(l_val) for l_val in val]
        return map(expand_path, val)


yaml.add_constructor('!path', expand_path_node, yaml.SafeLoader)


def load_file(filename):
    """
    Loads a YAML file and returns the document contents.

    :param filename: YAML file name.
    :type filename: unicode
    :return: Contents of the YAML file.
    :rtype: any
    """
    with open(filename, 'r') as f:
        return yaml.safe_load(f)


def load_map(stream, name=None, check_integrity=True):
    """
    Loads a ContainerMap configuration from a YAML document stream.

    :param stream: YAML stream.
    :type stream: file
    :param name: Name of the ContainerMap. If not provided, will be attempted to read from a ``name`` attribute on the
      document root level.
    :type name: unicode
    :param check_integrity: Performs a brief integrity check; default is ``True``.
    :type check_integrity: bool
    :return: A ContainerMap object.
    :rtype: ContainerMap
    """
    map_dict = yaml.safe_load(stream)
    if isinstance(map_dict, dict):
        map_name = name or map_dict.pop('name', None)
        if not map_name:
            raise ValueError("No map name provided, and none found in YAML stream.")
        return ContainerMap(map_name, map_dict, check_integrity=check_integrity)
    raise ValueError("Valid map could not be decoded.")


def load_map_file(filename, name=None, check_integrity=True):
    """
    Loads a ContainerMap configuration from a YAML file.

    :param filename: YAML file name.
    :type filename: unicode
    :param name: Name of the ContainerMap. If ``None`` will attempt to find a ``name`` element on the root level of
      the document; an empty string names the map according to the file, without extension.
    :type name: unicode
    :param check_integrity: Performs a brief integrity check; default is ``True``.
    :type check_integrity: bool
    :return: A ContainerMap object.
    :rtype: ContainerMap
    """
    if name == '':
        base_name = os.path.basename(filename)
        map_name, __, __ = os.path.basename(base_name).rpartition(os.path.extsep)
    else:
        map_name = name
    with open(filename, 'r') as f:
        return load_map(f, name=map_name, check_integrity=check_integrity)