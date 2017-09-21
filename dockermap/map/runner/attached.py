# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from docker.utils import create_host_config

from ...functional import resolve_value
from ..action import VolumeUtilAction
from ..config.client import USE_HC_MERGE
from ..input import ItemType
from ..policy.utils import get_instance_volumes
from .utils import update_kwargs, get_preparation_cmd


PREPARATION_TMP_PATH = '/volume-tmp'


class AttachedConfigMixin(object):
    def get_attached_preparation_create_kwargs(self, action, volume_container, volume_alias, kwargs=None):
        """
        Generates keyword arguments for the Docker client to prepare an attached container (i.e. adjust user and
        permissions).

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode | str
        :param volume_alias: Volume alias that is used for map references, for looking up paths.
        :type volume_alias: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        client_config = action.client_config
        config_id = action.config_id
        policy = self._policy
        if client_config.supports_volumes:
            path = PREPARATION_TMP_PATH
        else:
            path = resolve_value(policy.default_volume_paths[config_id.map_name][volume_alias])
        user = policy.volume_users[config_id.map_name][volume_alias]
        permissions = policy.volume_permissions[config_id.map_name][volume_alias]
        cmd = ' && '.join(get_preparation_cmd(user, permissions, path))
        if not cmd:
            return None
        c_kwargs = dict(
            image=policy.core_image,
            command=cmd,
            user='root',
            network_disabled=True,
        )
        hc_extra_kwargs = kwargs.pop('host_config', None) if kwargs else None
        use_host_config = client_config.use_host_config
        if use_host_config:
            if client_config.supports_volumes:
                c_kwargs['volumes'] = [PREPARATION_TMP_PATH]
            hc_kwargs = self.get_attached_preparation_host_config_kwargs(action, None, volume_container,
                                                                         kwargs=hc_extra_kwargs)
            if hc_kwargs:
                if use_host_config == USE_HC_MERGE:
                    c_kwargs.update(hc_kwargs)
                else:
                    c_kwargs['host_config'] = create_host_config(version=client_config.version, **hc_kwargs)
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_attached_preparation_host_config_kwargs(self, action, container_name, volume_container, kwargs=None):
        """
        Generates keyword arguments for the Docker client to set up the HostConfig for preparing an attached container
        (i.e. adjust user and permissions) or start the preparation.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container name or id. Set ``None`` when included in kwargs for ``create_container``.
        :type container_name: unicode | str | NoneType
        :param volume_container: Name of the volume or name of the container that shares the volume.
        :type volume_container: unicode | str
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        if action.client_config.supports_volumes:
            c_kwargs = dict(binds=['{0}:{1}'.format(volume_container, PREPARATION_TMP_PATH)])
        else:
            c_kwargs = dict(volumes_from=[volume_container])
        if container_name:
            c_kwargs['container'] = container_name
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs

    def get_attached_preparation_wait_kwargs(self, action, container_name, kwargs=None):
        """
        Generates keyword arguments for waiting for a container when preparing a volume. The container name may be
        the container being prepared, or the id of the container calling preparation commands.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param container_name: Container name or id. Set ``None`` when included in kwargs for ``create_container``.
        :type container_name: unicode | str | NoneType
        :param kwargs: Additional keyword arguments to complement or override the configuration-based values.
        :type kwargs: dict | NoneType
        :return: Resulting keyword arguments.
        :rtype: dict
        """
        c_kwargs = dict(container=container_name)
        client_config = action.client_config
        c_kwargs = dict(container=container_name)
        wait_timeout = client_config.get('wait_timeout')
        if wait_timeout is not None:
            c_kwargs['timeout'] = wait_timeout
        update_kwargs(c_kwargs, kwargs)
        return c_kwargs


class AttachedPreparationMixin(AttachedConfigMixin):
    """
    Utility mixin for preparing attached containers with file system owners and permissions.
    """
    action_method_names = [
        (ItemType.VOLUME, VolumeUtilAction.PREPARE, 'prepare_attached'),
    ]
    prepare_local = True
    policy_options = ['prepare_local']

    def _prepare_container(self, client, action, volume_container, volume_alias):
        """
        Runs a temporary container for preparing an attached volume for a container configuration.

        :param client: Docker client.
        :type client: docker.Client
        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param volume_container: Name of the container that shares the volume.
        :type volume_container: unicode | str
        :param volume_alias: Volume alias that is used for map references, for looking up paths.
        :type volume_alias: unicode | str
        """
        apc_kwargs = self.get_attached_preparation_create_kwargs(action, volume_container, volume_alias)
        if not apc_kwargs:
            return
        a_wait_kwargs = self.get_attached_preparation_wait_kwargs(action, volume_container)
        client.wait(volume_container, **a_wait_kwargs)
        temp_container = client.create_container(**apc_kwargs)
        temp_id = temp_container['Id']
        try:
            if action.client_config.use_host_config:
                client.start(temp_id)
            else:
                aps_kwargs = self.get_attached_preparation_host_config_kwargs(action, temp_id, volume_container)
                client.start(**aps_kwargs)
            temp_wait_kwargs = self.get_attached_preparation_wait_kwargs(action, temp_id)
            client.wait(temp_id, **temp_wait_kwargs)
        finally:
            client.remove_container(temp_id)

    def prepare_attached(self, action, a_name, **kwargs):
        """
        Prepares an attached volume for a container configuration.

        :param action: Action configuration.
        :type action: dockermap.map.runner.ActionConfig
        :param a_name: The full name or id of the container sharing the volume.
        :type a_name: unicode | str
        """
        client = action.client
        config_id = action.config_id
        policy = self._policy
        if action.container_map.use_attached_parent_name:
            v_alias = '{0.config_name}.{0.instance_name}'.format(config_id)
        else:
            v_alias = config_id.instance_name
        user = policy.volume_users[config_id.map_name][v_alias]
        permissions = policy.volume_permissions[config_id.map_name][v_alias]

        if not (self.prepare_local and hasattr(client, 'run_cmd')):
            return self._prepare_container(client, action, a_name, v_alias)
        if action.client_config.supports_volumes:
            volume_detail = client.inspect_volume(a_name)
            local_path = volume_detail['Mountpoint']
        else:
            instance_detail = client.inspect_container(a_name)
            volumes = get_instance_volumes(instance_detail, False)
            path = resolve_value(policy.default_volume_paths[config_id.map_name][v_alias])
            local_path = volumes.get(path)
            if not local_path:
                raise ValueError("Could not locate local path of volume alias '{0}' / "
                                 "path '{1}' in container {2}.".format(action.config_id.instance_name, path, a_name))
        return [
            client.run_cmd(cmd)
            for cmd in get_preparation_cmd(user, permissions, local_path)
        ]
