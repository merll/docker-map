# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
from collections import defaultdict

import six

from ....functional import resolve_value
from ...input import NetworkEndpoint
from ...policy.utils import init_options
from .. import State, StateFlags
from ..base import NetworkBaseState


log = logging.getLogger(__name__)


def _check_network_driver_opts(network_config, instance_detail):
    driver_opts = init_options(network_config.driver_options)
    if not driver_opts:
        return True
    opts = {option_key: option_value
            for option_key, option_value in six.iteritems(instance_detail['Options'])}
    for c_key, c_val in six.iteritems(driver_opts):
        if resolve_value(c_val) != opts.get(c_key):
            return False
    return True


class NetworkEndpointRegistry(object):
    def __init__(self, nname_func, cname_func, hostname_func, containers, default_networks):
        self._nname = nname_func
        self._cname = cname_func
        self._hostname = hostname_func
        self._containers = containers
        self._default_networks = list(default_networks.keys())
        self._endpoints = defaultdict(set)
        for network_detail in six.itervalues(default_networks):
            self.register_network(network_detail)

    def register_network(self, detail):
        network_id = detail['Id']
        for c_id, c_detail in six.iteritems(detail.get('Containers') or {}):
            self._endpoints[c_id].add((network_id, c_detail['EndpointID']))

    def check_container_config(self, config_id, c_config, detail):
        if not detail['Config'].get('NetworkDisabled', False):
            i_networks = detail['NetworkSettings'].get('Networks', {})
            connected_network_names = set(i_networks.keys())
        else:
            i_networks = {}
            connected_network_names = set()
        c_net_mode = c_config.network_mode or 'default'
        if c_config.networks:
            named_endpoints = [(self._nname(config_id.map_name, cn_config.network_name), cn_config)
                               for cn_config in c_config.networks]
        elif c_net_mode in ('default', 'bridge'):
            named_endpoints = [(d_name, NetworkEndpoint(d_name))
                               for d_name in self._default_networks]
        elif c_net_mode == 'none':
            named_endpoints = []
        else:
            if isinstance(c_net_mode, tuple):
                cc_name = self._cname(config_id.map_name, *c_net_mode)
                cc_name_mode = 'container:{0}'.format(cc_name)
                cc_id = self._containers.get(cc_name)
                if cc_id:
                    cn_names = (cc_name_mode, 'container:{0}'.format(cc_id))
                else:
                    cn_names = (cc_name_mode, )
            else:
                cc_name = None
                cn_names = (c_net_mode, )
            i_net_mode = detail['HostConfig']['NetworkMode']
            if i_net_mode not in cn_names and not any(cn_name in connected_network_names for cn_name in cn_names):
                log.debug("Configurations network mode %s not matching instance mode %s. Additional connections: %s.",
                          cn_names, i_net_mode, connected_network_names)
                return (StateFlags.NETWORK_LEFT | StateFlags.NETWORK_DISCONNECTED), {
                    'left': connected_network_names,
                    'disconnected': [NetworkEndpoint(cc_name)] if cc_name else []
                }
            return StateFlags.NONE, {}
        configured_network_names = {ce[0] for ce in named_endpoints}
        reset_networks = []
        if detail['State']['Running']:
            network_endpoints = self._endpoints.get(detail['Id'], set())
            disconnected_networks = []
            for ref_n_name, cn_config in named_endpoints:
                log.debug("Checking network %s.", ref_n_name)
                if ref_n_name not in connected_network_names:
                    log.debug("Network %s not found in container connections.", ref_n_name)
                    disconnected_networks.append(cn_config)
                    continue
                network_detail = i_networks[ref_n_name]
                c_alias_set = set(cn_config.aliases or ())
                if c_alias_set and not c_alias_set.issubset(network_detail.get('Aliases')):
                    log.debug("Aliases in network %s differ or are not present.", ref_n_name)
                    reset_networks.append((ref_n_name, cn_config))
                    continue
                if (network_detail['NetworkID'], network_detail['EndpointID']) not in network_endpoints:
                    log.debug("Network endpoint not found in %s (%s): %s", ref_n_name, network_detail['NetworkID'],
                              network_detail['EndpointID'])
                    reset_networks.append((ref_n_name, cn_config))
                    continue
                if cn_config.links:
                    linked_names = {'{0}:{1}'.format(self._cname(config_id.map_name, lc_name),
                                                     lc_alias or self._hostname(lc_name))
                                    for lc_name, lc_alias in cn_config.links}
                else:
                    linked_names = set()
                if set(network_detail.get('Links', []) or ()) != linked_names:
                    log.debug("Links in %s differ from configuration: %s.", ref_n_name, network_detail.get('Links', []))
                    reset_networks.append((ref_n_name, cn_config))
                    continue
        else:
            # In this case the endpoints are not registered in the network.
            disconnected_networks = list(configured_network_names - connected_network_names)
        s_flags = StateFlags.NONE
        extra = {}
        if disconnected_networks:
            log.debug("Container is not connected to configured networks: %s.", disconnected_networks)
            s_flags |= StateFlags.NETWORK_DISCONNECTED
            extra['disconnected'] = disconnected_networks
        if reset_networks:
            log.debug("Container is connected, but with different settings from the configuration: %s.", reset_networks)
            s_flags |= StateFlags.NETWORK_MISMATCH
            extra['reconnect'] = reset_networks
        left_networks = connected_network_names - configured_network_names
        if left_networks:
            log.debug("Container is connected to the following networks that it is not configured for: %s.",
                      left_networks)
            s_flags |= StateFlags.NETWORK_LEFT
            extra['left'] = left_networks
        return s_flags, extra


class UpdateNetworkState(NetworkBaseState):
    def __init__(self, *args, **kwargs):
        super(UpdateNetworkState, self).__init__(*args, **kwargs)
        self.endpoint_registry = None

    def get_state(self):
        base_state, state_flags, extra = super(UpdateNetworkState, self).get_state()
        if base_state == State.ABSENT or state_flags & StateFlags.NEEDS_RESET:
            return base_state, state_flags, extra

        self.endpoint_registry.register_network(self.detail)
        if (self.detail['Driver'] != resolve_value(self.config.driver) or
                not _check_network_driver_opts(self.config, self.detail) or
                self.detail['Internal'] != resolve_value(self.config.internal)):
            state_flags |= StateFlags.MISC_MISMATCH
        return base_state, state_flags, extra
