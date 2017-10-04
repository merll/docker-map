# -*- coding: utf-8 -*-
from collections import namedtuple
import sys

from six import with_metaclass

from ..action import Action, ImageAction
from ..exceptions import ActionTypeException, ActionException
from ..input import ItemType
from ..policy import PolicyUtilMeta, PolicyUtil
from ...utils import format_image_tag

ActionConfig = namedtuple('ActionConfig', ['client_name', 'config_id', 'client_config', 'client',
                                           'container_map', 'config'])
ActionOutput = namedtuple('ActionOutput', ['client_name', 'config_id', 'action_type', 'result'])


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
        :type actions: list[dockermap.map.action.ItemAction]
        :return: Where the result is not ``None``, returns the output from the client. Note that this is a generator
          and needs to be consumed in order for all actions to be performed.
        :rtype: collections.Iterable[dict]
        """
        policy = self._policy
        for action in actions:
            config_id = action.config_id
            config_type = config_id.config_type
            client_config = policy.clients[action.client_name]
            client = client_config.get_client()
            c_map = policy.container_maps[config_id.map_name]

            if config_type == ItemType.CONTAINER:
                config = c_map.get_existing(config_id.config_name)
                item_name = policy.cname(config_id.map_name, config_id.config_name, config_id.instance_name)
            elif config_type == ItemType.VOLUME:
                a_parent_name = config_id.config_name if c_map.use_attached_parent_name else None
                item_name = policy.aname(config_id.map_name, config_id.instance_name, parent_name=a_parent_name)
                if client_config.supports_volumes:
                    config = c_map.get_existing_volume(config_id.config_name)
                else:
                    config = c_map.get_existing(config_id.config_name)
            elif config_type == ItemType.NETWORK:
                config = c_map.get_existing_network(config_id.config_name)
                item_name = policy.nname(config_id.map_name, config_id.config_name)
            elif config_type == ItemType.IMAGE:
                config = None
                item_name = format_image_tag(config_id.config_name, config_id.instance_name)
            else:
                raise ValueError("Invalid configuration type.", config_id.config_type)

            for action_type in action.action_types:
                try:
                    a_method = self.action_methods[(config_type, action_type)]
                except KeyError:
                    raise ActionTypeException(config_id, action_type)
                action_config = ActionConfig(action.client_name, action.config_id, client_config, client,
                                             c_map, config)
                try:
                    res = a_method(action_config, item_name, **action.extra_data)
                except Exception:
                    exc_info = sys.exc_info()
                    raise ActionException(exc_info, action.client_name, config_id, action_type)
                if res is not None:
                    yield ActionOutput(action.client_name, config_id, action_type, res)
