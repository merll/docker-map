# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from docker.utils.utils import create_host_config, create_networking_config, create_endpoint_config
from requests import Timeout
from six import text_type, iteritems
from six.moves import map

from ...functional import resolve_value
from ..action import Action
from ..config.client import USE_HC_MERGE
from ..input import ItemType, NotSet
from ..policy.utils import extract_user, update_kwargs, init_options, get_volumes
from . import AbstractRunner
from .attached import AttachedPreparationMixin
from .cmd import ExecMixin
from .network import NetworkUtilMixin
from .script import ScriptMixin
from .signal_stop import SignalMixin
from .utils import get_host_binds, get_port_bindings


log = logging.getLogger(__name__)


class DockerBaseRunnerMixin(object):
    action_method_names = [
        (ItemType.VOLUME, Action.CREATE, 'create_volume'),
        (ItemType.VOLUME, Action.START, 'start_volume'),
        (ItemType.VOLUME, Action.REMOVE, 'remove_volume'),

        (ItemType.CONTAINER, Action.CREATE, 'create_container'),
        (ItemType.CONTAINER, Action.START, 'start_container'),
        (ItemType.CONTAINER, Action.RESTART, 'restart'),
        (ItemType.CONTAINER, Action.STOP, 'stop'),
        (ItemType.CONTAINER, Action.REMOVE, 'remove_container'),
        (ItemType.CONTAINER, Action.KILL, 'kill'),
        (ItemType.CONTAINER, Action.WAIT, 'wait'),
    ]

    def create_volume(self, action, v_name, **kwargs):
        c_kwargs = self.get_attached_container_create_kwargs(action, v_name, kwargs=kwargs)
        return action.client.create_container(**c_kwargs)

    def start_volume(self, action, v_name, **kwargs):
        # TODO: Merge with create.
        if action.client_config.get('use_host_config'):
            res = action.client.start(v_name)
        else:
            c_kwargs = self.get_attached_container_host_config_kwargs(action, v_name, kwargs=kwargs)
            res = action.client.start(**c_kwargs)
        return res

    def remove_volume(self, action, c_name, **kwargs):
        # TODO: Currently this is a copy of remove_container. Vary implementation for directly using Docker volumes.
        c_kwargs = self.get_container_remove_kwargs(action, c_name, kwargs=kwargs)
        return action.client.remove_container(**c_kwargs)

    def create_container(self, action, c_name, **kwargs):
        c_kwargs = self.get_container_create_kwargs(action, c_name, kwargs=kwargs)
        return action.client.create_container(**c_kwargs)

    def start_container(self, action, c_name, **kwargs):
        if action.client_config.get('use_host_config'):
            return action.client.start(c_name)
        c_kwargs = self.get_container_host_config_kwargs(action, c_name, kwargs=kwargs)
        return action.client.start(**c_kwargs)

    def restart(self, action, c_name, **kwargs):
        c_kwargs = self.get_container_restart_kwargs(action, c_name, kwargs=kwargs)
        return action.client.restart(**c_kwargs)

    def stop(self, action, c_name, **kwargs):
        c_kwargs = self.get_container_stop_kwargs(action, c_name, kwargs=kwargs)
        try:
            return action.client.stop(**c_kwargs)
        except Timeout:
            log.warning("Container did not stop in time - sent SIGKILL.")
        return None

    def remove_container(self, action, c_name, **kwargs):
        c_kwargs = self.get_container_remove_kwargs(action, c_name, kwargs=kwargs)
        return action.client.remove_container(**c_kwargs)

    def kill(self, action, c_name, **kwargs):
        return action.client.kill(c_name, **kwargs)

    def wait(self, action, c_name, **kwargs):
        c_kwargs = self.get_container_wait_kwargs(action, c_name, kwargs=kwargs)
        return action.client.wait(c_name, **c_kwargs)


class DockerConfigMixin(object):
    def get_container_create_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create a container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        policy = self._policy
        client_config = action.client_config
        container_map = action.container_map
        container_config = action.config
        c_kwargs = dict(
            name=container_name,
            image=policy.image_name(container_config.image or action.config_id.config_name, container_map),
            volumes=get_volumes(container_map, container_config),
            user=extract_user(container_config.user),
            ports=[resolve_value(port_binding.exposed_port)
                   for port_binding in container_config.exposes if port_binding.exposed_port],
            hostname=policy.get_hostname(container_name, action.client_name) if container_map.set_hostname else None,
            domainname=resolve_value(client_config.get('domainname', container_map.default_domain)) or None,
        )
        if container_config.network_mode == 'none':
            c_kwargs['network_disabled'] = True
        elif client_config.supports_networks and container_config.networks:
            first_network = container_config.networks[0]
            c_kwargs['networking_config'] = create_networking_config({
                policy.nname(action.config_id.map_name, first_network.network_name): create_endpoint_config(
                    client_config.version, **self.get_network_create_endpoint_kwargs(action, first_network)
                )
            })
        hc_extra_kwargs = kwargs.pop('host_config', None) if kwargs else None
        use_host_config = client_config.get('use_host_config')
        if use_host_config:
            hc_kwargs = self.get_container_host_config_kwargs(action, None, kwargs=hc_extra_kwargs)
            if hc_kwargs:
                if use_host_config == USE_HC_MERGE:
                    c_kwargs.update(hc_kwargs)
                else:
                    c_kwargs['host_config'] = create_host_config(version=client_config.version, **hc_kwargs)
        update_kwargs(c_kwargs, init_options(container_config.create_options), kwargs)
        return c_kwargs

    def get_container_host_config_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig or start a container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id. Set ``None`` when included in kwargs for ``create_container``.
        :type container_name: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        def volume_str(u):
            vol = cname(map_name, u.volume)
            if u.readonly:
                return '{0}:ro'.format(vol)
            return vol

        container_map = action.container_map
        container_config = action.config
        client_config = action.client_config
        map_name = container_map.name
        policy = self._policy
        aname = policy.aname
        cname = policy.cname
        volumes_from = list(map(volume_str, action.config.uses))
        if container_map.use_attached_parent_name:
            volumes_from.extend([aname(map_name, attached, action.config_id.config_name)
                                 for attached in container_config.attaches])
        else:
            volumes_from.extend([aname(map_name, attached)
                                 for attached in container_config.attaches])
        c_kwargs = dict(
            links=[(cname(map_name, l_name), alias or policy.get_hostname(l_name))
                   for l_name, alias in container_config.links],
            binds=get_host_binds(container_map, container_config, action.config_id.instance_name),
            volumes_from=volumes_from,
            port_bindings=get_port_bindings(container_config, client_config),
        )
        network_mode = container_config.network_mode
        if isinstance(network_mode, tuple):
            c_kwargs['network_mode'] = 'container:{0}'.format(cname(map_name, *network_mode))
        elif isinstance(network_mode, text_type):
            c_kwargs['network_mode'] = network_mode
        if container_name:
            c_kwargs['container'] = container_name
        update_kwargs(c_kwargs, init_options(container_config.host_config), kwargs)
        return c_kwargs

    def get_attached_container_create_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create an attached container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        client_config = action.client_config
        path = resolve_value(action.container_map.volumes[action.config_id.instance_name])
        user = extract_user(action.config.user)
        c_kwargs = dict(
            name=container_name,
            image=self._policy.base_image,
            volumes=[path],
            user=user,
            network_disabled=True,
        )
        hc_extra_kwargs = kwargs.pop('host_config', None) if kwargs else None
        use_host_config = client_config.get('use_host_config')
        if use_host_config:
            hc_kwargs = self.get_attached_container_host_config_kwargs(action, None, kwargs=hc_extra_kwargs)
            if hc_kwargs:
                if use_host_config == USE_HC_MERGE:
                    c_kwargs.update(hc_kwargs)
                else:
                    c_kwargs['host_config'] = create_host_config(version=client_config.version, **hc_kwargs)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_attached_container_host_config_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig or start an attached container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id. Set ``None`` when included in kwargs for ``create_container``.
        :type container_name: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        if container_name:
            c_kwargs = {'container': container_name}
        else:
            c_kwargs = {}
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_container_restart_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to restart a container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(container=container_name)
        stop_timeout = action.config.stop_timeout
        if stop_timeout is NotSet:
            timeout = action.client_config.get('stop_timeout')
            if timeout is not None:
                c_kwargs['timeout'] = timeout
        elif stop_timeout is not None:
            c_kwargs['timeout'] = stop_timeout
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_container_wait_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to wait for a container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        timeout = action.client_config.get('wait_timeout')
        if timeout is not None:
            c_kwargs = {'timeout': timeout}
        else:
            c_kwargs = {}
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_container_stop_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to stop a container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            container=container_name,
        )
        stop_timeout = action.config.stop_timeout
        if stop_timeout is NotSet:
            timeout = action.client_config.get('stop_timeout')
            if timeout is not None:
                c_kwargs['timeout'] = timeout
        elif stop_timeout is not None:
            c_kwargs['timeout'] = stop_timeout
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_container_remove_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to remove a container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(container=container_name)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_network_create_kwargs(self, action, network_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to create a network.

        :param action: Action configuration.
        :type action: ActionConfig
        :param network_name: Network name or id.
        :type network_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        config = action.config
        c_kwargs = dict(
            name=network_name,
            driver=config.driver,
            options=config.driver_options,
        )
        if config.internal:
            c_kwargs['internal'] = True
        driver_opts = init_options(config.driver_options)
        if driver_opts:
            c_kwargs['options'] = {option_name: resolve_value(option_value)
                                   for option_name, option_value in iteritems(driver_opts)}
        update_kwargs(c_kwargs, init_options(config.create_options), kwargs)
        return c_kwargs

    def get_network_remove_kwargs(self, action, network_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to remove a network.

        :param action: Action configuration.
        :type action: ActionConfig
        :param network_name: Network name or id.
        :type network_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(net_id=network_name)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_network_create_endpoint_kwargs(self, action, endpoint_config, kwargs=None):
        """
        Generates keyword arguments for Docker's ``create_endpoint_config`` utility as well as for
        ``connect_container_to_network``.

        :param action: Action configuration.
        :type action: ActionConfig
        :param endpoint_config: Network endpoint configuration.
        :type endpoint_config: dockermap.map.input.NetworkEndpoint
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        map_name = action.config_id.map_name
        policy = self._policy
        c_kwargs = dict(
            ipv4_address=resolve_value(endpoint_config.ipv4_address),
            ipv6_address=resolve_value(endpoint_config.ipv6_address),
        )
        if endpoint_config.aliases:
            c_kwargs['aliases'] = list(map(resolve_value, endpoint_config.aliases))
        if endpoint_config.links:
            c_kwargs['links'] = [(policy.cname(map_name, l_name), alias or policy.get_hostname(l_name))
                                 for l_name, alias in endpoint_config.links]
        if endpoint_config.link_local_ips:
            c_kwargs['link_local_ips'] = list(map(resolve_value, endpoint_config.link_local_ips))
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_network_connect_kwargs(self, action, network_name, container_name, endpoint_config=None, kwargs=None):
        """
        Generates keyword arguments for the Docker client to add a container to a network.

        :param action: Action configuration.
        :type action: ActionConfig
        :param network_name: Network name or id.
        :type network_name: unicode | str
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param endpoint_config: Network endpoint configuration.
        :type endpoint_config: dockermap.map.input.NetworkEndpoint
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            container=container_name,
            net_id=network_name,
        )
        if endpoint_config:
            c_kwargs.update(self.get_network_create_endpoint_kwargs(action, endpoint_config))
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_network_disconnect_kwargs(self, action, network_name, container_name, kwargs=None):
        """
        Generates keyword arguments for the Docker client to remove a container from a network.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param network_name: Network name or id.
        :type network_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            container=container_name,
            net_id=network_name,
        )
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_exec_create_kwargs(self, action, container_name, exec_cmd, exec_user, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig or start a container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :param exec_cmd: Command to be executed.
        :type exec_cmd: unicode | str
        :param exec_user: User to run the command.
        :type exec_user: unicode | str
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(
            container=container_name,
            cmd=resolve_value(exec_cmd),
        )
        if exec_user is not None:
            c_kwargs['user'] = text_type(resolve_value(exec_user))
        elif action.config.user is not NotSet:
            c_kwargs['user'] = extract_user(action.config.user)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_exec_start_kwargs(self, action, container_name, exec_id, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig or start a container.

        :param action: Action configuration.
        :type action: ActionConfig
        :param container_name: Container name or id.
        :type container_name: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :param exec_id: Id of the exec instance.
        :type exec_id: long
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(exec_id=exec_id)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs


class DockerClientRunner(DockerBaseRunnerMixin, DockerConfigMixin, AttachedPreparationMixin, ExecMixin, SignalMixin,
                         ScriptMixin, NetworkUtilMixin, AbstractRunner):
    """
    Runs actions on a Docker client and returns results from the API.
    """
    pass
