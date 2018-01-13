# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import posixpath
from collections import namedtuple, Iterable

import re
import six

from .. import DEFAULT_PRESET_NETWORKS
from ..functional import lazy_type, uses_type_registry
from . import SimpleEnum


class ExecPolicy(SimpleEnum):
    RESTART = 'restart'
    INITIAL = 'initial'


class CmdCheck(SimpleEnum):
    FULL = 'full'
    PARTIAL = 'partial'
    NONE = 'none'


class ItemType(SimpleEnum):
    CONTAINER = 'container'
    VOLUME = 'volume'
    NETWORK = 'network'
    IMAGE = 'image'


SharedVolume = namedtuple('SharedVolume', ('name', 'readonly'))
SharedVolume.__new__.__defaults__ = False,
HostVolume = namedtuple('HostVolume', ('path', 'host_path', 'readonly'))
HostVolume.__new__.__defaults__ = False,
UsedVolume = namedtuple('UsedVolume', ('name', 'path', 'readonly'))
UsedVolume.__new__.__defaults__ = None, False
ContainerLink = namedtuple('ContainerLink', ('container', 'alias'))
ContainerLink.__new__.__defaults__ = None,
PortBinding = namedtuple('PortBinding', ('exposed_port', 'host_port', 'interface', 'ipv6'))
PortBinding.__new__.__defaults__ = None, None, False

EXEC_POLICY_RESTART = ExecPolicy.RESTART  # For backwards compatibility.
EXEC_POLICY_INITIAL = ExecPolicy.INITIAL  # For backwards compatibility.


CURRENT_DIR = '{0}{1}'.format(posixpath.curdir, posixpath.sep)


@six.python_2_unicode_compatible
class _NotSet(object):
    def __nonzero__(self):
        return False

    __bool__ = __nonzero__

    def __repr__(self):
        return "<Value not set>"

    def __str__(self):
        return "Not set"

    def __eq__(self, other):
        return isinstance(other, self.__class__)


NotSet = _NotSet()


def _get_list(value):
    """
    Wraps the given value in a list. Empty values are returned as ``None`` (unlike in ``get_list`` in this module).
    Lists and tuples are returned as lists. Single strings and registered types are wrapped in a list.

    :param value: Value to return as a list.
    :return: List with the provided value(s).
    :rtype: list
    """
    if not value:
        return None
    elif isinstance(value, (list, tuple)):
        return list(value)
    elif isinstance(value, six.string_types + (lazy_type, )) or uses_type_registry(value):
        return [value]
    raise ValueError("Invalid type; expected a list, tuple, or string type, found {0}.".format(
        type(value).__name__))


TIME_PATTERN = re.compile(r'(\d+)\s*([num]s|s|m)?')


def _get_nanoseconds(value):
    if value is None:
        return None
    elif not value:
        return 0
    elif not isinstance(value, six.string_types):
        return value
    match = TIME_PATTERN.match(value.strip())
    if not match:
        raise ValueError("Invalid time format.", value)
    value, unit = match.groups()
    int_val = int(value)
    if not unit or unit == 'ns':
        return int_val
    elif unit == 'us':
        return int_val * 1000
    elif unit == 'ms':
        return int_val * 1000000
    elif unit == 's':
        return int_val * 1000000000
    elif unit == 'm':
        return int_val * 60000000000
    raise ValueError("Invalid unit.", unit)


class NetworkEndpoint(namedtuple('NetworkEndpoint', ('network_name', 'aliases', 'links', 'ipv4_address', 'ipv6_address',
                                                     'link_local_ips'))):
    def __new__(cls, network_name, aliases=None, links=None, ipv4_address=None, ipv6_address=None, link_local_ips=None):
        return super(NetworkEndpoint, cls).__new__(cls, network_name, _get_list(aliases), ContainerLinkList(links),
                                                   ipv4_address, ipv6_address, _get_list(link_local_ips))


class ExecCommand(namedtuple('ExecCommand', ('cmd', 'user', 'policy'))):
    def __new__(cls, cmd, user=None, policy=ExecPolicy.RESTART):
        if isinstance(policy, six.string_types):
            policy = ExecPolicy(policy)
        return super(ExecCommand, cls).__new__(cls, cmd, user, policy)

    def _asdict(self):
        d = super(ExecCommand, self)._asdict()
        d['policy'] = self[2].value
        return d


class MapConfigId(namedtuple('MapConfigId', ('config_type', 'map_name', 'config_name', 'instance_name'))):
    def __new__(cls, config_type, map_name, config_name, instance_name=None):
        if isinstance(config_type, six.string_types):
            config_type = ItemType(config_type)
        return super(MapConfigId, cls).__new__(cls, config_type, map_name, config_name, instance_name)

    def _asdict(self):
        d = super(MapConfigId, self)._asdict()
        d['config_type'] = self[0].value
        return d


class InputConfigId(namedtuple('InputConfigId', ('config_type', 'map_name', 'config_name', 'instance_names'))):
    def __new__(cls, config_type, map_name, config_name, instance_names=None):
        if isinstance(config_type, six.string_types):
            config_type = ItemType(config_type)
        return super(InputConfigId, cls).__new__(cls, config_type, map_name, config_name, instance_names)

    def _asdict(self):
        d = super(InputConfigId, self)._asdict()
        d['config_type'] = self[0].value
        return d


class HealthCheck(namedtuple('HealthCheck', ('test', 'interval', 'timeout', 'retries', 'start_period'))):
    def __new__(cls, test, interval=None, timeout=None, retries=None, start_period=None):
        if not test or test == 'NONE':
            test = None
        elif isinstance(test, (tuple, list)) and test[0] not in ('NONE', 'CMD', 'CMD-SHELL'):
            test_args = ['CMD']
            test_args.extend(test)
            test = test_args
        return super(HealthCheck, cls).__new__(cls, test, _get_nanoseconds(interval), _get_nanoseconds(timeout),
                                              retries, _get_nanoseconds(start_period))

    def _asdict(self):
        d = super(HealthCheck, self)._asdict()
        return {k: v
                for k, v in six.iteritems(d)
                if v or k == 'test'}


def _get_listed_tuples(value, element_type, conversion_func, **kwargs):
    if value is None:
        return []
    elif isinstance(value, element_type) or uses_type_registry(value):
        return [value]
    elif isinstance(value, six.string_types):
        return [conversion_func(value, **kwargs)]
    elif isinstance(value, dict):
        return [conversion_func(e, **kwargs) for e in six.iteritems(value)]
    elif isinstance(value, Iterable):
        return [conversion_func(e, **kwargs) for e in value]
    raise ValueError("Invalid type; expected {0}, list, tuple, or dict; found {1}.".format(
        element_type.__name__, type(value).__name__))


class NamedTupleList(list):
    element_type = None

    def __init__(self, seq=()):
        cls = self.__class__
        if isinstance(seq, cls):
            values = seq
        else:
            values = _get_listed_tuples(seq, cls.element_type, self.get_type_item)
        list.__init__(self, values)

    def append(self, item):
        cls = self.__class__
        if not isinstance(item, cls.element_type):
            item = self.get_type_item(item)
        list.append(self, item)

    def extend(self, iterable):
        cls = self.__class__
        if isinstance(iterable, cls):
            values = iterable
        else:
            values = _get_listed_tuples(iterable, cls.element_type, self.get_type_item)
        list.extend(self, values)

    def insert(self, index, item):
        cls = self.__class__
        if not isinstance(item, cls.element_type):
            item = self.get_type_item(item)
        list.insert(self, index, item)

    def get_type_item(self, value):
        raise NotImplementedError()


def is_path(value):
    """
    Checks whether the given value represents a path, i.e. a string which starts with an indicator for absolute or
    relative paths.

    :param value: Value to check.
    :return: ``True``, if the value appears to be representing a path.
    :rtype: bool
    """
    return value and isinstance(value, six.string_types) and (value[0] == posixpath.sep or value[:2] == CURRENT_DIR)


def read_only(value):
    """
    Checks whether the given value indicates a read-only access for a volume. For simplicity, this is any
    ``True``-equivalent value that except for the string "rw" (read-write).

    :param value: Value to check.
    :return: ``True`` if the volume is to be read-only.
    :rtype: bool
    """
    return value and value != 'rw'


def bool_if_set(value):
    """
    Converts the value to a boolean, unless it is `NotSet`.

    :param value: Value to convert.
    :return: Boolean
    :rtype: bool | _NotSet
    """
    if value is not NotSet:
        return bool(value)
    return value


def get_list(value):
    """
    Wraps the given value in a list. ``None`` returns an empty list. Lists and tuples are returned as lists. Single
    strings and registered types are wrapped in a list.

    :param value: Value to return as a list.
    :return: List with the provided value(s).
    :rtype: list
    """
    if value is None:
        return []
    elif value is NotSet:
        return NotSet
    elif isinstance(value, (list, tuple)):
        return list(value)
    elif isinstance(value, six.string_types + (lazy_type, )) or uses_type_registry(value):
        return [value]
    raise ValueError("Invalid type; expected a list, tuple, or string type, found {0}.".format(
        type(value).__name__))


def _shared_host_volume_from_tuple(*values):
    v_len = len(values)
    if v_len == 3:
        return HostVolume(values[0], values[1], read_only(values[2]))
    elif v_len == 2:
        v0, v1 = values
        if isinstance(v1, (list, tuple)):
            sv_len = len(v1)
            v1_0 = v1[0]
            if sv_len == 2:
                return HostVolume(v0, v1_0, read_only(v1[1]))
            elif sv_len == 1:
                if isinstance(v1_0, bool) or v1_0 in ('ro', 'rw'):
                    return SharedVolume(v0, read_only(v1_0))
                return HostVolume(v0, v1_0)
            raise ValueError("Nested list in {0} must have exactly one or two entries; found "
                             "{1}.".format(values, sv_len))
        elif isinstance(v1, bool) or v1 in ('ro', 'rw'):
            return SharedVolume(v0, read_only(v1))
        return HostVolume(v0, v1)
    elif v_len == 1:
        return SharedVolume(values[0])
    raise ValueError("Invalid element length; only tuples and lists of length 1-3 can be converted to a "
                     "HostVolume or SharedVolume tuple. Found length {0}.".format(v_len))


def _shared_used_volume_from_tuple(*values):
    v_len = len(values)
    if v_len == 3:
        return UsedVolume(values[0], values[1], read_only(values[2]))
    elif v_len == 2:
        v0, v1 = values
        if isinstance(v1, (list, tuple)):
            sv_len = len(v1)
            v1_0 = v1[0]
            if sv_len == 2:
                return UsedVolume(v0, v1_0, read_only(v1[1]))
            elif sv_len == 1:
                if isinstance(v1_0, bool) or v1_0 in ('ro', 'rw'):
                    return SharedVolume(v0, read_only(v1_0))
                return UsedVolume(v0, v1_0)
            raise ValueError("Nested list in {0} must have exactly one or two entries; found "
                             "{1}.".format(values, sv_len))
        elif isinstance(v1, bool) or v1 in ('ro', 'rw'):
            return SharedVolume(v0, read_only(v1))
        return UsedVolume(v0, v1)
    elif v_len == 1:
        return SharedVolume(values[0])
    raise ValueError("Invalid element length; only tuples and lists of length 1-3 can be converted to a "
                     "HostVolume or SharedVolume tuple. Found length {0}.".format(v_len))


def get_network_mode(value):
    """
    Generates input for the ``network_mode`` of a Docker host configuration. If it points at a container, the
    configuration of the container is returned.

    :param value: Network mode input.
    :type value: unicode | str | tuple | list | NoneType
    :return: Network mode or container to re-use the network stack of.
    :rtype: unicode | str | tuple | NoneType
    """
    if not value or value == 'disabled':
        return 'none'
    if isinstance(value, (tuple, list)):
        if len(value) == 2:
            return tuple(value)
        return ValueError("Tuples or lists need to have length 2 for container network references.")
    if value in DEFAULT_PRESET_NETWORKS:
        return value
    if value.startswith('container:'):
        return value
    if value.startswith('/'):
        return 'container:{0}'.format(value[1:])
    ref_name, __, ref_instance = value.partition('.')
    return ref_name, ref_instance or None


def get_healthcheck(value):
    """
    Converts input into a :class:`HealthCheck` tuple. Input can be passed as string, tuple, list, or a dictionary. If
    set to ``None``, the health check will be set to ``NONE``, i.e. override an existing configuration from the image.

    :param value: Health check input.
    :type value: unicode | str | tuple | list | NoneType
    :return: HealthCheck tuple
    :rtype: HealthCheck
    """
    if isinstance(value, HealthCheck):
        return value
    elif isinstance(value, six.string_types + (lazy_type,)) or uses_type_registry(value):
        return HealthCheck(value)
    elif isinstance(value, (tuple, list)):
        return HealthCheck(*value)
    elif isinstance(value, dict):
        return HealthCheck(**value)
    raise ValueError(
        "Invalid type; expected a list, tuple, dict, or string type, found {0}.".format(type(value).__name__))


class SharedHostVolumesList(NamedTupleList):
    """
    Converts a single value, a list or tuple, or a dictionary into a list of SharedVolume or HostVolume tuples for
    host volumes.
    """
    element_type = (SharedVolume, HostVolume)

    def get_type_item(self, value):
        """
        Converts the input to a ``SharedVolume`` or ``HostVolume`` tuple for a host bind. Input can be a single string, a
        list or tuple, or a single-entry dictionary.
        Single values are assumed to be volume aliases for read-write access. Tuples or lists with two elements, can be
        ``(alias, read-only indicator)``, or ``(container path, host path)``. The latter is assumed, unless the second
        element is boolean or a string of either ``ro`` or ``rw``, indicating read-only or read-write access for a volume
        alias. Three elements are always used as ``(container path, host path, read-only indicator)``.
        Nested values are unpacked, so that valid input formats are also ``{container path: (host path, read-only)}`` or
        ``(container_path: [host path, read-only])``.

        :param value: Input value for conversion.
        :return: A SharedVolume tuple
        :rtype: SharedVolume
        """
        if isinstance(value, (HostVolume, SharedVolume)):
            return value
        elif isinstance(value, six.string_types):
            return SharedVolume(value, False)
        elif isinstance(value, (list, tuple)):
            return _shared_host_volume_from_tuple(*value)
        elif isinstance(value, dict):
            v_len = len(value)
            if v_len == 1:
                k, v = list(value.items())[0]
                if k == 'name':
                    return SharedVolume(v)
                elif isinstance(v, (list, tuple)):
                    return _shared_host_volume_from_tuple(k, *v)
                return _shared_host_volume_from_tuple(k, v)
            elif 'path' in value:
                return HostVolume(**value)
            return SharedVolume(**value)
        raise ValueError(
            "Invalid type; expected a list, tuple, dict, or string type, found {0}.".format(type(value).__name__))


class AttachedVolumeList(NamedTupleList):
    """
    Converts a single value, a list or tuple, or a dictionary into a list of SharedVolume or UsedVolume tuples for
    attached volumes.
    """
    element_type = (SharedVolume, UsedVolume)

    def get_type_item(self, value):
        """
        Converts the given value to a ``UsedVolume`` or ``SharedVolume`` tuple for attached volumes. It
        accepts strings, lists, tuples, and dicts as input.

        For strings and collections of a single element, the first item is considered to be an alias for lookup on the map.
        It is converted to a ``SharedVolume`` tuple.
        For two-element collections, the first item defines a new volume alias that can be re-used by other instances and
        the second item is considered to be the mount point for the volume.
        All attached volumes are considered as read-write access.

        :param value: Input value for conversion.
        :return: UsedVolume or SharedVolume tuple.
        :rtype: UsedVolume | SharedVolume
        """
        if isinstance(value, (UsedVolume, SharedVolume)):
            if value.readonly:
                raise ValueError("Attached volumes should not be read-only.")
            return value
        elif isinstance(value, six.string_types):
            return SharedVolume(value)
        elif isinstance(value, (list, tuple)):
            v_len = len(value)
            if v_len == 2:
                if value[1]:
                    return UsedVolume(value[0], value[1])
                return SharedVolume(value[0])
            elif v_len == 1:
                return SharedVolume(value[0])
            raise ValueError("Invalid element length; only tuples and lists of length 1-2 can be converted to a "
                             "UsedVolume or SharedVolume tuple; found length {0}.".format(v_len))
        elif isinstance(value, dict):
            v_len = len(value)
            if v_len == 1:
                k, v = list(value.items())[0]
                if k == 'name':
                    return SharedVolume(v)
                return UsedVolume(k, v)
            elif 'path' in value:
                return UsedVolume(**value)
            return SharedVolume(**value)
        raise ValueError(
            "Invalid type; expected a list, tuple, dict, or string type, found {0}.".format(type(value).__name__))


class UsedVolumeList(NamedTupleList):
    """
    Converts a single value, a list or tuple, or a dictionary into a list of SharedVolume or UsedVolume tuples for
    used volumes.
    """
    element_type = (SharedVolume, UsedVolume)

    def get_type_item(self, value):
        """
        Converts the given value to a ``UsedVolume`` or ``SharedVolume`` tuple for used volumes. It accepts
        strings, lists, tuples, and dicts as input.

        Single values are assumed to be volume aliases for read-write access. Tuples or lists with two elements, can be
        ``(alias, read-only indicator)``, or ``(alias, mount path)``. The latter is assumed, unless the second
        element is boolean or a string of either ``ro`` or ``rw``, indicating read-only or read-write access for a volume
        alias. Three elements are always used as ``(alias, mount path, read-only indicator)``.
        Nested values are unpacked, so that valid input formats are also ``{alias: (mount path, read-only)}`` or
        ``(alias: [mount path, read-only])``.

        :param value: Input value for conversion.
        :return: UsedVolume or SharedVolume tuple.
        :rtype: UsedVolume | SharedVolume
        """
        if isinstance(value, (UsedVolume, SharedVolume)):
            return value
        elif isinstance(value, six.string_types):
            return SharedVolume(value, False)
        elif isinstance(value, (list, tuple)):
            return _shared_used_volume_from_tuple(*value)
        elif isinstance(value, dict):
            v_len = len(value)
            if v_len == 1:
                k, v = list(value.items())[0]
                if k == 'name':
                    return SharedVolume(v)
                elif isinstance(v, (list, tuple)):
                    return _shared_used_volume_from_tuple(k, *v)
                return _shared_used_volume_from_tuple(k, v)
            if 'path' in value:
                return UsedVolume(**value)
            return SharedVolume(**value)
        raise ValueError(
            "Invalid type; expected a list, tuple, dict, or string type, found {0}.".format(type(value).__name__))


class ContainerLinkList(NamedTupleList):
    """
    Converts a single value, a list or tuple, or a dictionary into a list of ContainerLink tuples.
    """
    element_type = ContainerLink

    def get_type_item(self, value):
        """
        Converts the input to a ContainerLink tuple. It can be from a single string, list, or tuple. Single values (also
        single-element lists or tuples) are considered a simple container link, whereas two-element items are read as
        ``(linked container, alias name)``.

        :param value: Input value for conversion.
        :return: ContainerLink tuple.
        :rtype: ContainerLink
        """
        if isinstance(value, ContainerLink):
            return value
        elif isinstance(value, six.string_types):
            return ContainerLink(value, None)
        elif isinstance(value, (list, tuple)):
            v_len = len(value)
            if 1 <= v_len <= 2:
                return ContainerLink(*value)
            raise ValueError("Invalid element length; only tuples and lists of length 1-2 can be converted to a "
                             "ContainerLink tuple. Found length {0}.".format(v_len))
        elif isinstance(value, dict):
            return ContainerLink(**value)
        raise ValueError(
            "Invalid type; expected a list, tuple, dict, or string type, found {0}.".format(type(value).__name__))


class ExecCommandList(NamedTupleList):
    """
    Converts a single value, a list or tuple, or a dictionary into a list of ExecCommand tuples.
    """
    element_type = ExecCommand

    def get_type_item(self, value):
        """
        Converts the input to a ExecCommand tuple. It can be from a single string, list, or tuple. Single values (also
        single-element lists or tuples) are considered a command string, whereas two-element items are read as
        ``(command string, user name)``.

        :param value: Input value for conversion.
        :return: ExecCommand tuple.
        :rtype: ExecCommand
        """
        if isinstance(value, ExecCommand):
            return value
        elif isinstance(value, six.string_types + (lazy_type,)):
            return ExecCommand(value)
        elif isinstance(value, (list, tuple)):
            v_len = len(value)
            if 1 <= v_len <= 3:
                return ExecCommand(*value)
            raise ValueError("Invalid element length; only tuples and lists of length 1-3 can be converted to a "
                             "ExecCommand tuple. Found length {0}.".format(v_len))
        elif isinstance(value, dict):
            return ExecCommand(**value)
        raise ValueError(
            "Invalid type; expected a list, tuple, dict, or string type, found {0}.".format(type(value).__name__))


class PortBindingList(NamedTupleList):
    """
    Converts a single value, a list or tuple, or a dictionary into a list of PortBinding tuples.
    """
    element_type = PortBinding

    def get_type_item(self, value):
        """
        Converts the given value to a ``PortBinding`` tuple. Input may come as a single value (exposed port for container
        linking only), a two-element tuple/list (port published on all host interfaces) or a three-element tuple/list
        (port published on a particular host interface). It can also be a dictionary with keyword arguments
        ``exposed_port``, ``host_port``, ``interface``, and ``ipv6``.

        :param value: Input value for conversion.
        :return: PortBinding tuple.
        :rtype: PortBinding
        """
        sub_types = six.string_types + six.integer_types
        if isinstance(value, PortBinding):
            return value
        elif isinstance(value, sub_types):  # Port only
            return PortBinding(value)
        elif isinstance(value, (list, tuple)):  # Exposed port, host port, and possibly interface
            v_len = len(value)
            if v_len == 1 and isinstance(value[0], sub_types):
                return PortBinding(value[0])
            if v_len == 2:
                if isinstance(value[1], dict):
                    return PortBinding(value[0], **value[1])
                ex_port, host_bind = value
                if isinstance(host_bind, sub_types + (lazy_type,)) or host_bind is None or uses_type_registry(
                        host_bind):
                    # Port, host port
                    return PortBinding(ex_port, host_bind)
                elif isinstance(host_bind, (list, tuple)):
                    s_len = len(host_bind)
                    if s_len in (2, 3):  # Port, (host port, interface) or (host port, interface, ipv6)
                        return PortBinding(ex_port, *host_bind)
                raise ValueError("Invalid sub-element type or length. Needs to be a port number or a tuple / list: "
                                 "(port, interface) or (port, interface, ipv6).")
            elif v_len in (3, 4):
                return PortBinding(*value)
            raise ValueError("Invalid element length; only tuples and lists of length 2 to 4 can be converted to a "
                             "PortBinding tuple.")
        elif isinstance(value, dict):
            return PortBinding(**value)
        raise ValueError(
            "Invalid type; expected a dict, list, tuple, int, or string type, found {0}.".format(type(value).__name__))


class NetworkEndpointList(NamedTupleList):
    """
    Converts a single value, a list or tuple, or a dictionary into a list of NetworkEndpoint tuples.
    """
    element_type = NetworkEndpoint

    def get_type_item(self, value):
        """
        Converts the input to a NetworkEndpoint tuple. It can be from a single-entry dictionary, single string, list, or
        tuple. Single values (also single-element lists or tuples) are considered a network name. Dictionaries can also
        contain nested dictionaries with keyword arguments to the NetworkEndpoint. Lists / tuples of length 2 are also
        checked for such dictionaries.

        :param value: Input value for conversion.
        :return: NetworkEndpoint tuple.
        :rtype: NetworkEndpoint
        """
        if isinstance(value, NetworkEndpoint):
            return value
        elif isinstance(value, six.string_types + (lazy_type,)):
            return NetworkEndpoint(value)
        elif isinstance(value, (list, tuple)):
            v_len = len(value)
            if v_len == 2 and isinstance(value[1], dict):
                return NetworkEndpoint(value[0], **value[1])
            elif 1 <= v_len <= 6:
                return NetworkEndpoint(*value)
            raise ValueError("Invalid element length; only dictionaries, pr tuples and lists of length 1-6 can be "
                             "converted to a NetworkEndpoint tuple. Found length {0}.".format(v_len))
        elif isinstance(value, dict):
            d_len = len(value)
            if d_len == 1:
                k, v = list(value.items())[0]
                if k == 'network_name':
                    return NetworkEndpoint(v)
                if not v:
                    return NetworkEndpoint(k)
                if isinstance(v, six.string_types):
                    return NetworkEndpoint(k, v)
                v_len = len(v)
                if isinstance(v, dict):
                    return NetworkEndpoint(k, **v)
                elif isinstance(v, (list, tuple)):
                    if 1 <= v_len <= 5:
                        return NetworkEndpoint(k, *v)
                    raise ValueError("Invalid sub-element length; lists and tuples of length 1-5 can be converted. "
                                     "Found length {0}.".format(v_len))
                raise ValueError(
                    "Invalid sub-element format; only dicts and tuples of length 1-5 can be converted. Found "
                    "type {0}.".format(type(value).__name__))
            return NetworkEndpoint(**value)
        raise ValueError(
            "Invalid type; expected a dict, list, tuple, or string type, found {0}.".format(type(value).__name__))


class InputConfigIdList(NamedTupleList):
    element_type = InputConfigId

    def __init__(self, seq=(), map_name=None, instances=None):
        if not instances:
            default_instances = None
        elif isinstance(instances, tuple):
            default_instances = instances
        elif isinstance(instances, list):
            default_instances = tuple(instances)
        elif isinstance(instances, six.string_types):
            default_instances = (instances,)
        else:
            raise ValueError("Invalid instances specification; expected string, list, or tuple, found "
                             "{0}.".format(type(instances).__name__))

        cls = self.__class__
        if isinstance(seq, cls):
            values = seq
        elif isinstance(seq, MapConfigId):
            if seq.instance_name:
                v_instances = (seq.instance_name,)
            else:
                v_instances = default_instances
            values = [InputConfigId(seq.config_type, seq.map_name, seq.config_name, v_instances)]
        else:
            values = _get_listed_tuples(seq, cls.element_type, self.get_type_item,
                                        map_name=map_name, instances=default_instances)
        list.__init__(self, values)

    def get_type_item(self, value, map_name=None, instances=None):
        """
        Converts the input to a InputConfigId tuple. It can be from a single string, list, or tuple. Single values
        (also single-element lists or tuples) are considered to be a container configuration on the default map. A string
        with two elements separated by a dot or two-element lists / tuples are considered to be referring to a specific
        map and configuration. Three strings concatenated with a dot or three-element lists / tuples are considered to be
        referring to a map, configuration, and instances. Multiple instances can be specified in the third element by
        passing a tuple or list.

        :param value: Input value for conversion.
        :param map_name: Map name; provides the default map name unless otherwise specified in ``value``.
        :type map_name: unicode | str
        :param instances: Instance names; instances to set if not otherwise specified in ``value``.
        :type instances: unicode | str | tuple[unicode | str | NoneType]
        :return: InputConfigId tuple.
        :rtype: InputConfigId
        """
        if isinstance(value, InputConfigId):
            return value
        elif isinstance(value, MapConfigId):
            if value.instance_name:
                v_instances = value.instance_name,
            else:
                v_instances = None
            return InputConfigId(value.config_type, value.map_name, value.config_name, v_instances or instances)
        elif isinstance(value, six.string_types):
            s_map_name, __, s_config_name = value.partition('.')
            if s_config_name:
                config_name, __, s_instance = s_config_name.partition('.')
                if s_instance:
                    s_instances = s_instance,
                else:
                    s_instances = None
            else:
                config_name = s_map_name
                s_map_name = map_name
                s_instances = None
            return InputConfigId(ItemType.CONTAINER, s_map_name, config_name, s_instances or instances)
        elif isinstance(value, (tuple, list)):
            v_len = len(value)
            if v_len == 3:
                v_instances = value[2]
                if not v_instances:
                    return InputConfigId(ItemType.CONTAINER, value[0], value[1])
                if isinstance(v_instances, tuple):
                    return InputConfigId(ItemType.CONTAINER, *value)
                elif isinstance(v_instances, list):
                    return InputConfigId(ItemType.CONTAINER, value[0], value[1], tuple(v_instances))
                elif isinstance(v_instances, six.string_types):
                    return InputConfigId(ItemType.CONTAINER, value[0], value[1], (v_instances,))
                raise ValueError(
                    "Invalid type of instance specification in '{0}'; expected a list, tuple, or string type, "
                    "found {1}.".format(value, type(v_instances).__name__), v_instances)
            elif v_len == 2:
                return InputConfigId(ItemType.CONTAINER, value[0] or map_name, value[1], instances)
            elif v_len == 1:
                return InputConfigId(ItemType.CONTAINER, map_name, value[0], instances)
            raise ValueError("Invalid element length; only tuples and lists of length 1-3 can be converted to a "
                             "InputConfigId tuple. Found length {0}.".format(v_len))
        elif isinstance(value, dict):
            kwargs = {
                'config_type': ItemType.CONTAINER,
                'map_name': map_name,
                'instance_names': instances,
            }
            kwargs.update(value)
            return InputConfigId(**kwargs)
        raise ValueError(
            "Invalid type; expected a list, tuple, dict, or string type, found {0}.".format(type(value).__name__))
