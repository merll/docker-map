# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..action import ImageAction
from ..input import ItemType
from .utils import update_kwargs

log = logging.getLogger(__name__)


class ImageMixin(object):
    action_method_names = [
        (ItemType.IMAGE, ImageAction.PULL, 'pull'),
    ]

    def __init__(self, *args, **kwargs):
        super(ImageMixin, self).__init__(*args, **kwargs)
        self._login_registries = set()

    def login(self, action, registry, **kwargs):
        """
        Logs in to a Docker registry.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param registry: Name of the registry server to login to.
        :type registry: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        log.info("Logging into registry %s.", registry)
        login_kwargs = {'registry': registry}
        auth_config = action.client_config.auth_configs.get(registry)
        if auth_config:
            log.debug("Registry auth config for %s found.", registry)
            login_kwargs.update(auth_config)
            insecure_registry = kwargs.get('insecure_registry')
            if insecure_registry is not None:
                login_kwargs['insecure_registry'] = insecure_registry
        else:
            raise KeyError("No login information found for registry.", registry)
        update_kwargs(login_kwargs, kwargs)
        res = action.client.login(**login_kwargs)
        if res:
            log.debug("User %(username)s logged into %(registry)s.", login_kwargs)
            self._login_registries.add(registry)
        return res

    def pull(self, action, image_name, **kwargs):
        """
        Pulls an image for a container configuration

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param image_name: Image name.
        :type image_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        config_id = action.config_id
        registry, __, image = config_id.config_name.rpartition('/')
        if registry and '.' in registry and registry not in self._login_registries:
            self.login(action, registry, insecure_registry=kwargs.get('insecure_registry'))
        log.info("Pulling image %s:%s.", config_id.config_name, config_id.instance_name)
        res = action.client.pull(repository=config_id.config_name, tag=config_id.instance_name, **kwargs)
        log.debug("Done pulling image %s:%s.", config_id.config_name, config_id.instance_name)
        self._policy.images[action.client_name].refresh_repo(config_id.config_name)
        log.debug("Refreshed image cache for repo %s.", config_id.config_name)
        return res
