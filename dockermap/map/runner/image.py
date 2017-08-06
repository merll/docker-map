# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ..action import ImageAction
from ..input import ItemType

log = logging.getLogger(__name__)


class ImageMixin(object):
    action_method_names = [
        (ItemType.IMAGE, ImageAction.PULL, 'pull'),
    ]

    def pull(self, action, **kwargs):
        """
        Pulls an image for a container configuration

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        """
        config_id = action.config_id
        log.info("Pulling image %s:%s.", config_id.config_name, config_id.instance_name)
        res = action.client.pull(repository=config_id.config_name, tag=config_id.instance_name, **kwargs)
        log.debug("Done pulling image %s:%s.", config_id.config_name, config_id.instance_name)
        return res
