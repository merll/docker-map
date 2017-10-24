# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
from operator import itemgetter

import six

from ..input import ItemType, MapConfigId, get_input_config_ids, InputConfigId

get_map_config = itemgetter(0, 1, 2)


def _get_nested_instances(group_items):
    instance_set = set()
    instance_add = instance_set.add
    return tuple(ni
                 for di in group_items
                 for ni in di[3] or (None, )
                 if ni not in instance_set and not instance_add(ni))


def _get_config_instances(config_type, c_map, config_name):
    if config_type == ItemType.CONTAINER:
        config = c_map.get_existing(config_name)
        if not config:
            raise KeyError(config_name)
        return config.instances
    elif config_type == ItemType.VOLUME:
        config = c_map.get_existing(config_name)
        if not config:
            raise KeyError(config_name)
        return config.attaches
    elif config_type == ItemType.NETWORK:
        config = c_map.get_existing_network(config_name)
        if not config:
            raise KeyError(config_name)
        return None,
    raise ValueError("Invalid configuration type.", config_type)


def expand_groups(config_ids, maps):
    """
    Iterates over a list of container configuration ids, expanding groups of container configurations.

    :param config_ids: List of container configuration ids.
    :type config_ids: collections.Iterable[dockermap.map.input.InputConfigId | dockermap.map.input.MapConfigId]
    :param maps: Extended container maps.
    :type maps: dict[unicode | str, dockermap.map.config.main.ContainerMap]
    :return: Expanded MapConfigId tuples.
    :rtype: collections.Iterable[dockermap.map.input.InputConfigId]
    """
    for config_id in config_ids:
        if config_id.map_name == '__all__':
            c_maps = six.iteritems(maps)
        else:
            c_maps = (config_id.map_name, maps[config_id.map_name]),
        if isinstance(config_id, InputConfigId):
            instance_name = config_id.instance_names
        elif isinstance(config_id, MapConfigId):
            instance_name = (config_id.instance_name, )
        else:
            raise ValueError("Expected InputConfigId or MapConfigId tuple; found {0}."
                             "".format(type(config_id).__name__))
        for map_name, c_map in c_maps:
            if config_id.config_name == '__all__' and config_id.config_type == ItemType.CONTAINER:
                for config_name in six.iterkeys(c_map.containers):
                    yield MapConfigId(config_id.config_type, map_name, config_name, instance_name)
            else:
                group = c_map.groups.get(config_id.config_name)
                if group is not None:
                    for group_item in group:
                        if isinstance(group_item, MapConfigId):
                            yield group_item
                        elif isinstance(group_item, six.string_types):
                            config_name, __, instance = group_item.partition('.')
                            yield MapConfigId(config_id.config_type, map_name, config_name,
                                              (instance, ) if instance else instance_name)
                        else:
                            raise ValueError("Invalid group item. Must be string or MapConfigId tuple; "
                                             "found {0}.".format(type(group_item).__name__))
                else:
                    yield MapConfigId(config_id.config_type, map_name, config_id.config_name, instance_name)


def expand_instances(config_ids, ext_maps):
    """
    Iterates over a list of input configuration ids, expanding configured instances if ``None`` is specified. Otherwise
    where instance names are specified as a tuple, they are expanded.

    :param config_ids: Iterable of container configuration ids or (map, config, instance names) tuples.
    :type config_ids: collections.Iterable[dockermap.map.input.InputConfigId] | collections.Iterable[tuple[unicode | str, unicode | str, unicode | str]]
    :param ext_maps: Dictionary of extended ContainerMap instances for looking up container configurations.
    :type ext_maps: dict[unicode | str, ContainerMap]
    :return: MapConfigId tuples.
    :rtype: collections.Iterable[dockermap.map.input.MapConfigId]
    """
    for type_map_config, items in itertools.groupby(sorted(config_ids, key=get_map_config), get_map_config):
        config_type, map_name, config_name = type_map_config
        instances = _get_nested_instances(items)
        c_map = ext_maps[map_name]
        try:
            c_instances = _get_config_instances(config_type, c_map, config_name)
        except KeyError:
            raise KeyError("Configuration not found.", type_map_config)
        if c_instances and None in instances:
            for i in c_instances:
                yield MapConfigId(config_type, map_name, config_name, i)
        else:
            for i in instances:
                yield MapConfigId(config_type, map_name, config_name, i)


def get_map_config_ids(value, maps, default_map_name=None, default_instances=None):
    """
    From a value, which can be a string, a iterable of strings, or MapConfigId tuple(s), generates a list of MapConfigId
    tuples with expanded groups, listing all input or configured instances, and sorted by map and configuration.

    :param value: Input value(s).
    :type value: str | unicode | dockermap.map.input.InputConfigId | collection.Iterable[str | unicode | dockermap.map.input.InputConfigId]
    :param maps: Dictionary with expanded container maps, for resolving groups, aliases (``'__all__'``), and configured
      instances in absence of instance specification in the input.
    :param default_map_name: Default map name that is used, in case it is not part of the input.
    :param default_instances: Default instance name list that is used, in case it is not specified in the input.
    :return: List of MapConfigId tuples.
    :rtype: list[dockermap.map.input.MapConfigId]
    """
    input_ids = get_input_config_ids(value, map_name=default_map_name, instances=default_instances)
    return list(expand_instances(expand_groups(input_ids, maps), maps))
