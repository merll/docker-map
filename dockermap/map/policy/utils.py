# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six


def extract_user(user):
    if not user and user != 0 and user != '0':
        return None
    if isinstance(user, tuple):
        return user[0]
    if isinstance(user, int):
        return six.text_type(user)
    return user.partition(':')[0]


def update_kwargs(kwargs, *updates):
    for update in updates:
        if not update:
            continue
        for key, u_item in six.iteritems(update):
            if not u_item:
                continue
            kw_item = kwargs.get(key)
            if isinstance(u_item, (tuple, list)):
                if kw_item:
                    kw_item.extend(u_item)
                else:
                    kwargs[key] = u_item[:]
            elif isinstance(u_item, dict):
                if kw_item:
                    kw_item.update(u_item)
                else:
                    kwargs[key] = u_item.copy()
            else:
                kwargs[key] = u_item


def init_options(options):
    if options:
        if callable(options):
            return options()
        return options
    return {}


def get_config(container_map, config_name):
    return container_map.get_existing(config_name)


def get_volume_path(container_map, alias):
    path = container_map.volumes.get(alias)
    if not path:
        raise ValueError("No path found for volume '{0}'.".format(alias))
    return path


def get_host_binds(container_map, config, instance):
    for alias, readonly in config.binds:
        share = container_map.host.get(alias, instance)
        if share:
            bind = {'bind': get_volume_path(container_map, alias), 'ro': readonly}
            yield share, bind


def get_existing_containers(container_status):
    return container_status.keys()


def get_running_containers(container_status):
    return set(container for container, status in six.iteritems(container_status) if status is True)
