# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from docker.utils import create_host_config

from ...functional import resolve_value
from ..action import UTIL_ACTION_PREPARE_CONTAINER
from ..config import USE_HC_MERGE
from ..policy.utils import update_kwargs, get_instance_volumes
from .utils import get_preparation_cmd


class AttachedConfigMixin(object):
    def get_attached_preparation_create_kwargs(self, config, volume_container, kwargs=None):
        """
        Generates keyword arguments for the Docker client to prepare an attached container (i.e. adjust user and
        permissions).

        :param config: Configuration.
        :type config: dockermap.map.runner.ActionConfig
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        client_config = config.client_config
        path = resolve_value(config.container_map.volumes[config.instance_name])
        cmd = get_preparation_cmd(config.container_config, path)
        if not cmd:
            return None
        c_kwargs = dict(
            image=self._policy.core_image,
            command=' && '.join(cmd),
            user='root',
            network_disabled=True,
        )
        hc_extra_kwargs = kwargs.pop('host_config', None) if kwargs else None
        use_host_config = client_config.get('use_host_config')
        if use_host_config:
            hc_kwargs = self.get_attached_preparation_host_config_kwargs(config, None, volume_container,
                                                                         kwargs=hc_extra_kwargs)
            if hc_kwargs:
                if use_host_config == USE_HC_MERGE:
                    c_kwargs.update(hc_kwargs)
                else:
                    c_kwargs['host_config'] = create_host_config(version=client_config.version, **hc_kwargs)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_attached_preparation_host_config_kwargs(self, config, container_name, volume_container, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig for preparing an attached container
        (i.e. adjust user and permissions) or start the preparation.

        :param config: Configuration.
        :type config: dockermap.map.runner.ActionConfig
        :param container_name: Container name or id. Set ``None`` when included in kwargs for ``create_container``.
        :type container_name: unicode | str | NoneType
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(volumes_from=[volume_container])
        if container_name:
            c_kwargs['container'] = container_name
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_attached_preparation_wait_kwargs(self, config, container_name, kwargs=None):
        """
        Generates keyword arguments for waiting for a container when preparing a volume. The container name may be
        the container being prepared, or the id of the container calling preparation commands.

        :param config: Configuration.
        :type config: dockermap.map.runner.ActionConfig
        :param container_name: Container name or id. Set ``None`` when included in kwargs for ``create_container``.
        :type container_name: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        client_config = config.client_config
        wait_timeout = client_config.get('wait_timeout')
        if wait_timeout is not None:
            c_kwargs = dict(timeout=wait_timeout)
            update_kwargs(c_kwargs, kwargs)
            return c_kwargs
        return kwargs


class AttachedPreparationMixin(AttachedConfigMixin):
    """
    Utility mixin for preparing attached containers with file system owners and permissions.
    """
    attached_action_method_names = [
        (UTIL_ACTION_PREPARE_CONTAINER, 'prepare_attached'),
    ]
    prepare_local = True
    policy_options = ['prepare_local']

    def _prepare_container(self, client, config, volume_container):
        """
        Runs a temporary container for preparing an attached volume for a container configuration.

        :param client: Docker client.
        :type client: docker.Client
        :param config: Configuration.
        :type config: dockermap.map.runner.ActionConfig
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode | str
        """
        apc_kwargs = self.get_attached_preparation_create_kwargs(config, volume_container)
        if not apc_kwargs:
            return
        images = self._policy.images[config.client_name]
        images.ensure_image(apc_kwargs['image'])
        a_wait_kwargs = self.get_attached_preparation_wait_kwargs(config, volume_container)
        client.wait(volume_container, **a_wait_kwargs)
        temp_container = client.create_container(**apc_kwargs)
        temp_id = temp_container['Id']
        try:
            if config.client_config.get('use_host_config'):
                client.start(temp_id)
            else:
                aps_kwargs = self.get_attached_preparation_host_config_kwargs(config, temp_id, volume_container)
                client.start(**aps_kwargs)
            temp_wait_kwargs = self.get_attached_preparation_wait_kwargs(config, temp_id)
            client.wait(temp_id, **temp_wait_kwargs)
        finally:
            client.remove_container(temp_id)

    def prepare_attached(self, config, a_name, **kwargs):
        """
        Prepares an attached volume for a container configuration.

        :param config: Configuration.
        :type config: dockermap.map.runner.ActionConfig
        :param a_name: The full name or id of the container sharing the volume.
        :type a_name: unicode | str
        """
        client = config.client
        if not (self.prepare_local and hasattr(client, 'run_cmd')):
            return self._prepare_container(client, config, a_name)
        instance_detail = client.inspect_container(a_name)
        volumes = get_instance_volumes(instance_detail)
        path = resolve_value(config.container_map.volumes[config.instance_name])
        local_path = volumes.get(path)
        if not local_path:
            raise ValueError("Could not locate local path of volume alias '{0}' / "
                             "path '{1}' in container {2}.".format(config.instance_name, path, a_name))
        return [
            client.run_cmd(cmd)
            for cmd in get_preparation_cmd(config.container_config, local_path)
        ]
