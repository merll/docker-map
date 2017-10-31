# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from ....functional import resolve_value
from ...input import UsedVolume
from ...policy.utils import get_shared_volume_path
from .. import State, StateFlags
from ..base import VolumeBaseState


log = logging.getLogger(__name__)


class AbstractSingleVfsCheck(object):
    """
    :type config_id: dockermap.map.input.MapConfigId
    :type container_map: dockermap.map.config.main.ContainerMap
    :type policy: dockermap.map.policy.base.BasePolicy
    :type vfs_paths: dict[tuple, unicode | str]
    :type instance_volumes: dict[unicode | str, unicode | str]
    """
    def __init__(self, config_id, container_map, policy, vfs_paths, instance_volumes):
        self._config_id = config_id
        self._container_map = container_map
        self._policy = policy
        self._vfs_paths = vfs_paths
        self._instance_volumes = instance_volumes

    def check_bind(self, config, instance):
        config_id = self._config_id
        for shared_volume in config.binds:
            bind_path, host_path = get_shared_volume_path(self._container_map, shared_volume, instance)
            instance_vfs = self._instance_volumes.get(bind_path)
            log.debug("Checking host bind. Config / container instance:\n%s\n%s", host_path, instance_vfs)
            if not (instance_vfs and host_path == instance_vfs):
                return False
            self._vfs_paths[config_id.config_name, config_id.instance_name, bind_path] = instance_vfs
        return True

    def check_attached(self, config, parent_name):
        raise NotImplemented("To be implemented by subclasses.")

    def check_used_vfs(self, used, used_alias, parent_name, default_path):
        raise NotImplemented("To be implemented by subclasses.")

    def check_used(self, config):
        config_id = self._config_id
        default_paths = self._policy.default_volume_paths[config_id.map_name]
        use_parent_name = self._container_map.use_attached_parent_name
        for used in config.uses:
            used_volume = used.name
            ref_c_name, __, ref_i_name = used_volume.partition('.')
            if use_parent_name:
                default_path = default_paths.get(used_volume)
                if default_path is None:
                    default_path = default_paths.get(ref_i_name)
                used_config, used_alias = ref_c_name, ref_i_name
            elif not ref_i_name:
                default_path = default_paths.get(ref_c_name)
                used_alias = ref_c_name
                used_config = None
            else:
                default_path = None
                used_config = None
                used_alias = None
            if default_path is not None:
                if not self.check_used_vfs(used, used_alias, used_config, default_path):
                    return False
                continue
            log.debug("Looking up dependency %s (instance %s).", ref_c_name, ref_i_name)
            ref_config = self._container_map.get_existing(ref_c_name)
            if ref_config:
                for share in ref_config.shares:
                    ref_shared_path = resolve_value(share)
                    i_shared_path = self._instance_volumes.get(ref_shared_path)
                    shared_vfs = self._vfs_paths.get((ref_c_name, ref_i_name, ref_shared_path))
                    log.debug("Checking shared path %s. Parent instance / dependent container instance:\n%s\n%s",
                              share, shared_vfs, i_shared_path)
                    if shared_vfs != i_shared_path:
                        return False
                    self._vfs_paths[config_id.config_name, config_id.instance_name, ref_shared_path] = i_shared_path
                self.check_bind(ref_config, ref_i_name)
                self.check_attached(ref_config, ref_c_name)
            else:
                raise ValueError("Volume alias or container reference could not be resolved.", used_volume)
        return True


class SingleLegacyVfsCheck(AbstractSingleVfsCheck):
    def check_attached(self, config, parent_name):
        config_id = self._config_id
        default_paths = self._policy.default_volume_paths[config_id.map_name]
        use_parent_name = self._container_map.use_attached_parent_name
        for attached in config.attaches:
            a_name = '{0}.{1}'.format(parent_name, attached.name) if use_parent_name else attached.name
            if isinstance(attached, UsedVolume):
                attached_path = attached.path
            else:
                attached_path = resolve_value(default_paths[attached.name])
            attached_vfs = self._vfs_paths.get((a_name, None, attached_path))
            instance_vfs = self._instance_volumes.get(attached_path)
            log.debug("Checking attached %s path. Attached instance / dependent container instance:\n%s\n%s",
                      attached, attached_vfs, instance_vfs)
            if not (instance_vfs and attached_vfs == instance_vfs):
                return False
            self._vfs_paths[config_id.config_name, config_id.instance_name, attached_path] = instance_vfs
        return True

    def check_used_vfs(self, used, used_alias, parent_name, default_path):
        used_path = resolve_value(default_path)
        used_vfs = self._vfs_paths.get((used.name, None, used_path))
        instance_path = self._instance_volumes.get(used_path)
        log.debug("Checking used %s path. Parent instance / dependent container instance:\n%s\n%s",
                  used.name, used_vfs, instance_path)
        if used_vfs and used_vfs == instance_path:
            return True
        return False


class SingleVolumeVfsCheck(AbstractSingleVfsCheck):
    def check_attached(self, config, parent_name):
        config_id = self._config_id
        parent_name = parent_name if self._container_map.use_attached_parent_name else None
        policy = self._policy
        default_paths = policy.default_volume_paths[config_id.map_name]
        for attached in config.attaches:
            v_name = policy.aname(config_id.map_name, attached.name, parent_name)
            log.debug("Checking for attached volume %s.", v_name)
            if isinstance(attached, UsedVolume):
                path = resolve_value(attached.path)
            else:
                path = resolve_value(default_paths.get(attached.name))
            if not path:
                raise ValueError("Reference path for attached volume could be resolved.", attached)
            instance_volume_name = self._instance_volumes.get(path)
            log.debug("Checking attached %s volume at %s. Configured name / instance name:\n%s\n%s",
                      attached.name, path, v_name, instance_volume_name)
            if not instance_volume_name or instance_volume_name != v_name:
                log.debug("No volume for destination path %s not found.", path)
                return False
        return True

    def check_used_vfs(self, used, used_alias, parent_name, default_path):
        if isinstance(used, UsedVolume):
            used_path = resolve_value(used.path)
        else:
            used_path = resolve_value(default_path)
        v_name = self._policy.aname(self._config_id.map_name, used_alias, parent_name)
        instance_volume_name = self._instance_volumes.get(used_path)
        log.debug("Checking used %s volume at %s. Configured name / instance name:\n%s\n%s",
                  used.name, used_path, v_name, instance_volume_name)
        if instance_volume_name and instance_volume_name == v_name:
            return True
        return False


class AbstractVolumeChecker(object):
    def __init__(self, policy):
        self._vfs_paths = {}
        self._policy = policy

    def register_attached(self, alias, parent_name, mapped_path, path):
        pass

    def get_vfs_check(self, config_id, container_map, instance_volumes):
        raise NotImplemented("To be implemented by subclass.")

    def check(self, config_id, container_map, container_config, instance_volumes):
        vfs = self.get_vfs_check(config_id, container_map, instance_volumes)
        for share in container_config.shares:
            cr_shared_path = resolve_value(share)
            self._vfs_paths[config_id.config_name, config_id.instance_name, cr_shared_path] = instance_volumes.get(share)
        if not vfs.check_bind(container_config, config_id.instance_name):
            return False
        if not vfs.check_attached(container_config, config_id.config_name):
            return False
        if not vfs.check_used(container_config):
            return False
        return True


class ContainerLegacyVolumeChecker(AbstractVolumeChecker):
    def register_attached(self, alias, parent_name, mapped_path, path):
        volume_name = '{0}.{1}'.format(parent_name, alias) if parent_name else alias
        self._vfs_paths[volume_name, None, mapped_path] = path

    def get_vfs_check(self, config_id, container_map, instance_volumes):
        return SingleLegacyVfsCheck(config_id, container_map, self._policy, self._vfs_paths, instance_volumes)


class ContainerVolumeChecker(AbstractVolumeChecker):
    def get_vfs_check(self, config_id, container_map, instance_volumes):
        return SingleVolumeVfsCheck(config_id, container_map, self._policy, self._vfs_paths, instance_volumes)


class VolumeUpdateState(VolumeBaseState):
    def get_state(self):
        base_state, state_flags, extra = super(VolumeUpdateState, self).get_state()
        if base_state == State.ABSENT or state_flags & StateFlags.NEEDS_RESET:
            return base_state, state_flags, extra

        if self.detail['Driver'] != self.config.driver:
            log.debug("Volume driver %s does not match configuration %s.", self.detail['Driver'], self.config.driver)
            return base_state, state_flags | StateFlags.MISC_MISMATCH, extra
        elif self.detail['Options'] != self.config.driver_options:
            log.debug("Volume driver options %s do not match the configured options: %s.",
                      self.detail['Options'], self.config.driver_options)
            return base_state, state_flags | StateFlags.MISC_MISMATCH, extra
        return base_state, state_flags, extra
