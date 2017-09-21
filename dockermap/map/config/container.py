# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from . import ConfigurationObject, CP
from ..input import (get_shared_host_volumes, get_attached_volumes, get_used_volumes, get_container_links,
                     get_network_mode, get_port_bindings, get_exec_commands, get_network_endpoints, bool_if_set)


def _merge_first(current, update_list):
    if not update_list:
        return
    update_dict = {item[0]: item for item in update_list}
    for i, item in enumerate(current):
        if item[0] in update_dict:
            current[i] = update_dict.pop(item[0])
    if update_dict:
        current.extend(u for u in update_list if u[0] in update_dict)


class ContainerConfiguration(ConfigurationObject):
    """
    Class to maintain resources that are associated with a container.
    """
    abstract = CP(default=False, input_func=bool, merge_func=False)
    extends = CP(list, merge_func=False)
    image = CP()
    instances = CP(list)
    clients = CP(list)
    shares = CP(list)
    binds = CP(list, input_func=get_shared_host_volumes, merge_func=_merge_first)
    attaches = CP(list, input_func=get_attached_volumes, merge_func=_merge_first)
    uses = CP(list, input_func=get_used_volumes, merge_func=_merge_first)
    links = CP(list, input_func=get_container_links)
    exposes = CP(list, input_func=get_port_bindings, merge_func=_merge_first)
    user = CP()
    permissions = CP()
    stop_timeout = CP()
    stop_signal = CP()
    network_mode = CP(input_func=get_network_mode)
    networks = CP(list, input_func=get_network_endpoints, merge_func=_merge_first)
    exec_commands = CP(list, input_func=get_exec_commands)
    persistent = CP(input_func=bool_if_set)
    create_options = CP(dict)
    host_config = CP(dict)

    DOCSTRINGS = {
        'abstract': "Marks this configuration as abstract, so that it can not be used for container actions directly, "
                    "but for basing other configurations on.",
        'extends': "Bases this configuration on one or more configurations.",
        'image': "The base image of the container. If set to `None`, the containers will be instantiated with an image "
                 "that has the same name.",
        'instances': "Separate instances of a container, if any. By default there is one instance of each container. "
                     "If set, containers will be created for each instance in the format "
                     "`map_name.container_name.instance`.",
        'clients': "Set this to client names that you would like to limit container instantiation to. This overrides "
                   "clients specified globally for a map.",
        'shares': "Shared volumes for a container.",
        'binds': "The host volume shares for a container. These will be added to the shared volumes, and mapped to a "
                 "host volume.",
        'attaches': "Names of volumes that are assigned to this container, and that can be shared with other "
                    "containers. For hosts that do not support named volumes, an empty container will "
                    "be created that shares a single volume. This can be in the syntax ``alias: mount path`` "
                    "(dict, tuple, list) or just ``alias`` if the mount path is set in the ``volumes`` property of "
                    "the container map.",
        'uses': "Volumes used from other containers. This can be a combination of attached volume aliases, and "
                "container names if all volumes are to be used of that container. For hosts that support named volumes "
                "this can be specified as ``volume alias: mount path`` (as a dict, list, or tuple); otherwise only "
                "volume names can be provided here and the mount path of the origin is re-used (attached or container "
                "volume).",
        'links': "Linked containers. Links are set in the format `ContainerLink(name, alias)`, where the name is the "
                 "linked container's name, and the alias name the alias to use for this container instance.",
        'exposes': """\
            Ports and (virtual) interface name that a network service is exposed on.

            The following formats are considered as valid input and will be converted to a list of ``PortBinding``
            tuples:

            * Dictionary with container exposed ports as keys, and either host port and interface, or only the host port
              as values.
            * A list or tuple with elements

              * tuple or list: container exposed port, host port - for mapping all host addresses;
              * tuple or list: container exposed port, (host port, host interface) as nested tuple or list;
              * tuple or list: container exposed port, host port, host interface;
              * container exposed port only - will not be published, but is available to linked containers.

            If the host port, but no interface is set, the port will be published to all interfaces (as this is the
            Docker default). Otherwise the relevant IP address to expose the service on will be looked up at run-time.\
            """,
        'user': "User name / group or id to launch the container with and to which the owner is set in attached "
                "containers. Can be set as a string (`user_name` or `user_name:group`), ids (e.g. `user_id:group_id`), "
                "tuple (`(user_name, group_name)`), or int (`user_id`).",
        'permissions': "Permission flags to be set for attached volumes. Can be in any notation accepted by `chmod`.",
        'stop_timeout': "Individual timeout (in seconds) for stopping a container, i.e. the time between sending a "
                        "``SIGTERM`` and a ``SIGKILL`` to the container.",
        'stop_signal': "By default Docker sends ``SIGTERM`` to containers on stop or restart. This may not always be "
                       "the best signal to get the main process to shut down properly. This property can for example "
                       "be set to ``SIGINT``, where more appropriate.",
        'network_mode': "Networking to apply to this container. If not ``bridge`` or ``host`` (as described in the "
                        "docker-py docs), tries to locate a container configuration on this map. Prefixed with ``/`` "
                        "assumes the full container name. Setting it to ``disabled`` deactivates networking for the "
                        "container.",
        'networks': "Names of configured networks for this container to join.",
        'exec_commands': "Commands to run as soon as the container is started. Set in the format "
                         "`ExecCommand(cmd, user, policy)`, where the user is set to the same as this configuration's "
                         "user by default (or root, if not available). The policy decides when to start the command.",
        'persistent': "Set this to ``True`` for containers that are only started to share a volume, but exist "
                      "immediately. Such containers are restarted and not removed during cleanup.",
        'create_options': "Additional keyword args for :meth:`docker.client.Client.create_container`.",
        'host_config': "Additional keyword args for :meth:`docker.client.Client.start` or HostConfig options to pass "
                       "to :meth:`docker.client.Client.create`.",
    }

    def __repr__(self):
        if self.extends:
            ext_str = 'extends {0}'.format(self.extends)
        else:
            ext_str = ''
        return ("{1}{0.__class__.__name__} {2} shares: {0.shares}; binds: {0.binds}; uses: {0.uses}; "
                "attaches: {0.attaches}").format(self, 'Abstract ' if self.abstract else '', ext_str)
