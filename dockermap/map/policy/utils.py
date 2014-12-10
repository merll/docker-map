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
    return dict()


def get_host_binds(container_map, config, instance):
    def _gen_binds():
        for alias, readonly in config.binds:
            share = container_map.host.get(alias, instance)
            if share:
                bind = dict(bind=container_map.volumes[alias], ro=readonly)
                yield share, bind

    return dict(_gen_binds())
