# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import six

from ...input import CmdCheck
from ..base import DependencyStateGenerator
from .container import UpdateContainerState
from .network import UpdateNetworkState, NetworkEndpointRegistry
from .volume import ContainerLegacyVolumeChecker, ContainerVolumeChecker, VolumeUpdateState


class UpdateStateGenerator(DependencyStateGenerator):
    """
    Generates states for updating configured containers. Before checking each configuration, for each image the latest
    version is pulled from the registry, but only if :attr:`UpdateStateGenerator.pull_before_update` is set to ``True``.

    An attached container is considered outdated, if its image id does not correspond with the current base
    image, and :attr:`~ContainerUpdateMixin.update_persistent` is set to ``True``.
    Any other container is considered outdated, if

      - any of its attached volumes' paths does not match (i.e. they are not actually sharing the same virtual
        file system), or
      - the image id does not correspond with the configured image (e.g. because the image has been updated), or
      - environment variables have been changed in the configuration, or
      - command or entrypoint have been set or changed, or
      - network ports differ from what is specified in the configuration.

    In addition, the default state implementation applies, considering nonexistent containers or containers that
    cannot be restarted.
    """
    container_state_class = UpdateContainerState
    network_state_class = UpdateNetworkState
    volume_state_class = VolumeUpdateState

    update_persistent = False
    check_exec_commands = CmdCheck.FULL
    policy_options = ['update_persistent', 'check_exec_commands']

    def __init__(self, policy, kwargs):
        super(UpdateStateGenerator, self).__init__(policy, kwargs)
        self._volume_checkers = {
            client_name: ContainerVolumeChecker(policy)
            if client_config.supports_volumes
            else ContainerLegacyVolumeChecker(policy)
            for client_name, client_config in six.iteritems(policy.clients)
        }
        default_network_details = {
            client_name: {
                n_name: client_config.get_client().inspect_network(n_name)
                for n_name in policy.default_network_names
                if n_name in policy.network_names[client_name]
            }
            for client_name, client_config in six.iteritems(policy.clients)
            if client_config.supports_networks
        }
        self._network_registries = {
            client_name: NetworkEndpointRegistry(policy.nname, policy.cname, policy.get_hostname,
                                                 policy.container_names[client_name],
                                                 default_network_details[client_name])
            for client_name, network_details in six.iteritems(default_network_details)
        }

    def get_container_state(self, client_name, *args, **kwargs):
        c_state = super(UpdateStateGenerator, self).get_container_state(client_name, *args, **kwargs)
        c_state.volume_checker = self._volume_checkers[client_name]
        c_state.endpoint_registry = self._network_registries.get(client_name)
        return c_state

    def get_network_state(self, client_name, *args, **kwargs):
        n_state = super(UpdateStateGenerator, self).get_network_state(client_name, *args, **kwargs)
        n_state.endpoint_registry = self._network_registries.get(client_name)
        return n_state
