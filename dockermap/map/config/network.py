# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from ..input import bool_if_set
from ..config import ConfigurationObject, CP


class NetworkConfiguration(ConfigurationObject):
    driver = CP()
    driver_options = CP(dict)
    internal = CP(input_func=bool_if_set)
    create_options = CP(dict)

    DOCSTRINGS = {
        'driver': "The network driver name.",
        'driver_options': "Custom options to the driver.",
        'internal': "Whether the network is internal.",
        'create_options': "Additional keyword arguments to creating the network.",
    }
