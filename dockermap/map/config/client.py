# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from distutils.version import StrictVersion

from ...client.base import DockerClientWrapper
from ...docker_api import CLIENT_FEATURES
from .. import DictMap

USE_HC_MERGE = 'merge'


FEATURE_VERSIONS = [
    (fn, StrictVersion(str(fv)))
    for fn, fv in CLIENT_FEATURES
]


class ClientConfiguration(DictMap):
    """
    Configuration class for storing values that are specific to a particular Docker client, and generating client
    instances.

    :param base_url: URL of the Docker Remote API.
    :type base_url: unicode | str
    :param version: Docker Remote API version.
    :type version: unicode | str
    :param timeout: Request timeout.
    :type timeout: int
    :param args: Further initializing dictionary with values.
    :param kwargs: Further initializing keyword arguments.
    """
    init_kwargs = 'base_url', 'version', 'timeout', 'tls'
    client_constructor = DockerClientWrapper

    def __init__(self, base_url=None, version=None, timeout=None, *args, **kwargs):
        self._base_url = base_url
        self._version = version
        self._features = features = kwargs.pop('features', {})
        for f_name, __ in FEATURE_VERSIONS:
            if f_name in kwargs:
                features[f_name] = kwargs.pop(f_name)
        self._timeout = timeout
        if 'interfaces' in kwargs:
            self._interfaces = DictMap(kwargs.pop('interfaces'))
        else:
            self._interfaces = DictMap()
        if 'interfaces_ipv6' in kwargs:
            self._interfaces_ipv6 = DictMap(kwargs.pop('interfaces_ipv6'))
        else:
            self._interfaces_ipv6 = DictMap()
        self._auth_configs = kwargs.pop('auth_configs', None) or {}
        self._client = kwargs.pop('client', None)
        super(ClientConfiguration, self).__init__(*args, **kwargs)
        self.update_settings(version=version)

    @classmethod
    def from_client(cls, client):
        """
        Constructs a configuration object from an existing client instance. If the client has already been created with
        a configuration object, returns that instance.

        :param client: Client object to derive the configuration from.
        :type client: docker.client.Client
        :return: ClientConfiguration
        """
        if hasattr(client, 'client_configuration'):
            return client.client_configuration
        kwargs = {'client': client}
        for attr in cls.init_kwargs:
            if hasattr(client, attr):
                kwargs[attr] = getattr(client, attr)
        if hasattr(client, 'api_version'):
            kwargs['version'] = client.api_version
        return cls(**kwargs)

    def update_settings(self, **kwargs):
        version = kwargs.pop('version', None)
        if version and version != 'auto':
            try:
                version_str = StrictVersion(str(version))
            except ValueError:
                pass
            else:
                features = self._features
                for f_name, f_version in FEATURE_VERSIONS:
                    features.setdefault(f_name, version_str >= f_version)

    def get_init_kwargs(self):
        """
        Generates keyword arguments for creating a new Docker client instance.

        :return: Keyword arguments as defined through this configuration.
        :rtype: dict
        """
        init_kwargs = {}
        for k in self.init_kwargs:
            if k in self.core_property_set:
                init_kwargs[k] = getattr(self, k)
            elif k in self:
                init_kwargs[k] = self[k]
        return init_kwargs

    def get_client(self):
        """
        Retrieves or creates a client instance from this configuration object. If instantiated from this configuration,
        the resulting object is also cached in the property ``client`` and a reference to this configuration is stored
        on the client object.

        :return: Client object instance.
        :rtype: docker.client.Client
        """
        client = self._client
        if not client:
            self._client = client = self.client_constructor(**self.get_init_kwargs())
            client.client_configuration = self
            # Client might update the version number after construction.
            updated_version = getattr(client, 'api_version', None)
            if updated_version:
                self.version = updated_version
        return client

    @property
    def base_url(self):
        """
        Base URL of the Docker client. If this is changed after the client has been instantiated, it is not updated on
        the client.

        :return: URL
        :rtype: unicode | str
        """
        return self._base_url

    @base_url.setter
    def base_url(self, value):
        self._base_url = value

    @property
    def version(self):
        """
        API version of the Docker client. When set to ``auto`` it is updated with the Docker hosts' version number
        upon instantiation of the client. If this is changed after the client has been instantiated, it is not updated
        on the client.

        :return: Docker API version.
        :rtype: unicode | str
        """
        return self._version

    @version.setter
    def version(self, value):
        self._version = value
        self.update_settings(version=value)

    @property
    def timeout(self):
        """
        Timeout in seconds of the Docker client. If changed after client instantiation, the client's value is updated
        as well.

        :return:
        """
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self._timeout = value
        if self._client:
            self._client.timeout = value

    @property
    def interfaces(self):
        """
        Dictionary of network interface settings as specific for the client. Note that the interface name is virtual,
        i.e. only used for assigning addresses.

        :return: Network interface configuration.
        :rtype: DictMap
        """
        return self._interfaces

    @interfaces.setter
    def interfaces(self, value):
        self._interfaces = DictMap(value)

    @property
    def interfaces_ipv6(self):
        """
        Same as :attr:`ClientConfiguration.interfaces`, but for assigning IPv6 interface addresses.

        :return: Network interface configuration.
        :rtype: DictMap
        """
        return self._interfaces_ipv6

    @interfaces_ipv6.setter
    def interfaces_ipv6(self, value):
        self._interfaces_ipv6 = DictMap(value)

    @property
    def auth_configs(self):
        """
        Authentication to use for access to Docker Registry servers.

        :return: Dictionary of authentication info per registry to use.
        :rtype: dict[unicode | str, dict]
        """
        return self._auth_configs

    @auth_configs.setter
    def auth_configs(self, value):
        self._auth_configs = value

    @property
    def client(self):
        """
        Assigned Client instance.

        :return: Client object.
        :rtype: docker.client.Client
        """
        return self._client

    @client.setter
    def client(self, value):
        self._client = value

    @property
    def features(self):
        """
        Supported client features.

        :return: Feature dict.
        :rtype: dict
        """
        if not self._client:
            self.get_client()
        return self._features
