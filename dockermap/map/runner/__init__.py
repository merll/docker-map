# -*- coding: utf-8 -*-
from collections import namedtuple

from six import with_metaclass

from ..input import ITEM_TYPE_CONTAINER, ITEM_TYPE_VOLUME, ITEM_TYPE_NETWORK
from ..action import ACTION_CREATE, ACTION_REMOVE
from ..policy import PolicyUtilMeta, PolicyUtil

ActionConfig = namedtuple('ActionConfig', ['client_name', 'client_config', 'client',
                                           'map_name', 'container_map',
                                           'config_name', 'config', 'instance_name'])


class RunnerMeta(PolicyUtilMeta):
    def __init__(cls, name, bases, dct):
        cls._a_methods = action_methods = []
        for base in bases:
            if hasattr(base, 'action_method_names'):
                action_methods.extend(base.action_method_names)
        method_names = dct.get('action_method_names')
        if method_names:
            action_methods.extend(method_names)
        super(RunnerMeta, cls).__init__(name, bases, dct)


class AbstractRunner(with_metaclass(RunnerMeta, PolicyUtil)):
    def __new__(cls, *args, **kwargs):
        instance = super(AbstractRunner, cls).__new__(cls, *args, **kwargs)
        instance.action_methods = {
            (item_type, action_name): getattr(instance, action_method)
            for item_type, action_name, action_method in cls._a_methods
        }
        return instance

    def run_actions(self, actions):
        """
        Runs the given lists of attached actions and instance actions on the client.

        :param actions: Actions to apply.
        :type actions: dockermap.map.action.ClientMapActions
        :return: Where the result is not ``None``, returns the output from the client. Note that this is a generator
          and needs to be consumed in order for all actions to be performed.
        :rtype: collections.Iterable[dict]
        """
        policy = self._policy

        client_config = policy.clients[actions.client_name]
        client = client_config.get_client()
        c_map = policy.container_maps[actions.map_name]

        for action in actions.actions:
            if action.config_type == ITEM_TYPE_CONTAINER:
                config = c_map.get_existing(action.config_name)
                item_name = policy.cname(actions.map_name, action.config_name, action.instance_name)
                existing_items = policy.container_names[actions.client_name]
            elif action.config_type == ITEM_TYPE_VOLUME:
                # TODO
                config = c_map.get_existing(action.config_name)
                a_parent_name = action.config_name if c_map.use_attached_parent_name else None
                item_name = policy.aname(cma.map_name, action.instance_name, parent_name=a_parent_name)
                existing_items = policy.container_names[actions.client_name]
            elif action.config_type == ITEM_TYPE_NETWORK:
                # TODO
                config = None
                item_name = policy.nname(actions.map_name, action.config_name)
                existing_items = policy.network_names[action.client_name]
            else:
                raise ValueError("Invalid configuration type.", action.config_type)

            for action_type in action.action_types:
                try:
                    a_method = self.action_methods[(action.config_type, action.action_type)]
                except KeyError:
                    raise ValueError("Invalid action.", action.config_type, action.action_type)
                action_config = ActionConfig(action.client_name, client_config, client,
                                             action.map, c_map,
                                             action.config, config, action.instance_name)
                res = a_method(action_config, item_name, **action.extra_data)
                if action_type == ACTION_CREATE:
                    existing_items.add(item_name)
                elif action_type == ACTION_REMOVE:
                    existing_items.discard(item_name)
                if res is not None:
                    yield res
