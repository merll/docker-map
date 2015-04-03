.. _container_advanced:

Advanced library usage
======================

Docker-Map can be used within Python applications directly, but also be used as a base implementation for other
libraries. This section covers some areas that may be relevant when implementing enhancements, like `Docker-Fabric`_.

.. _policy_implementation:

Implementing policies
---------------------
Policies are briefly mentioned in the section :ref:`applying_maps`. Generally, policies take available
container configurations as input. They have direct access to the Docker client. They can therefore check the current
state of containers and their running configuration against the container maps, as well as perform all other client
actions.

For example, :class:`~dockermap.map.policy.resume.ResumeUpdatePolicy` is the default built-in policy. Besides checking
on the container state, it also checks if volumes shared by a container into the virtual filesystem are consistent
with the volumes a dependent container is using. There is also a :class:`~dockermap.map.policy.simple.SimplePolicy`,
which only considers dependencies of containers, but does not perform additional checks.

If you feel like creating your own container handling logic, you do not have to start from scratch. First of all,
built-in classes are based on :class:`~dockermap.map.policy.base.BasePolicy`, which provides many methods that are
separate container actions:

* :meth:`~dockermap.map.policy.base.BasePolicy.get_create_kwargs`,
  :meth:`~dockermap.map.policy.base.BasePolicy.get_start_kwargs`,
  :meth:`~dockermap.map.policy.base.BasePolicy.get_restart_kwargs`,
  :meth:`~dockermap.map.policy.base.BasePolicy.get_stop_kwargs`, and
  :meth:`~dockermap.map.policy.base.BasePolicy.get_remove_kwargs` generate keyword arguments from container
  configurations, that can be used directly on the Docker client;
* :meth:`~dockermap.map.policy.base.BasePolicy.get_attached_create_kwargs`,
  :meth:`~dockermap.map.policy.base.BasePolicy.get_attached_preparation_create_kwargs`,
  :meth:`~dockermap.map.policy.base.BasePolicy.get_attached_start_kwargs`, and
  :meth:`~dockermap.map.policy.base.BasePolicy.get_attached_preparation_start_kwargs` have similar functionality for
  attached containers;
* :meth:`~dockermap.map.policy.base.BasePolicy.get_clients` provides the clients, that a client configuration should be
  applied to;
* :meth:`~dockermap.map.policy.base.BasePolicy.get_dependencies` and
  :meth:`~dockermap.map.policy.base.BasePolicy.get_dependents` return the dependency path of
  containers for deciding in which order to create, start, stop, and remove containers;
* :meth:`~dockermap.map.policy.base.BasePolicy.get_default_client_name`,
  :meth:`~dockermap.map.policy.base.BasePolicy.cname`,
  :meth:`~dockermap.map.policy.base.BasePolicy.resolve_cname`,
  :meth:`~dockermap.map.policy.base.BasePolicy.iname`,
  :meth:`~dockermap.map.policy.base.BasePolicy.get_hostname`, and
  :meth:`~dockermap.map.policy.base.BasePolicy.get_domainname` generate inputs for aforementioned functions. They can
  be overridden separately.

A subclass of :class:`~dockermap.map.policy.base.BasePolicy` needs to implement the following abstract methods:

* :meth:`~dockermap.map.policy.base.BasePolicy.create_actions`
* :meth:`~dockermap.map.policy.base.BasePolicy.start_actions`
* :meth:`~dockermap.map.policy.base.BasePolicy.stop_actions`
* :meth:`~dockermap.map.policy.base.BasePolicy.remove_actions`

The following methods are optional for implementation:

* :meth:`~dockermap.map.policy.base.BasePolicy.startup_actions` (would be in most cases a combination of
  :meth:`~dockermap.map.policy.base.BasePolicy.create_actions` and
  :meth:`~dockermap.map.policy.base.BasePolicy.start_actions`)
* :meth:`~dockermap.map.policy.base.BasePolicy.shutdown_actions` (could combine
  :meth:`~dockermap.map.policy.base.BasePolicy.stop_actions` and
  :meth:`~dockermap.map.policy.base.BasePolicy.remove_actions`)
* :meth:`~dockermap.map.policy.base.BasePolicy.restart_actions`
* :meth:`~dockermap.map.policy.base.BasePolicy.update_actions`

The built-in policies are composed by mixins which use an intermediate element - implementations of
:class:`~dockermap.map.policy.base.AbstractActionGenerator`. The reason for this abstraction is the similarity between
following dependencies. The only individual method to be implemented is
:meth:`~dockermap.map.policy.base.AbstractActionGenerator.generate_item_actions`.
For :meth:`~dockermap.map.policy.base.AbstractActionGenerator.get_dependency_path`, one of the mixins
:class:`dockermap.map.policy.base.ForwardActionGeneratorMixin` or
:class:`dockermap.map.policy.base.ReverseActionGeneratorMixin` can be re-used. You may also want to just override
specific actions and for the rest re-use the built-in mixins.

Additionally, the :class:`~dockermap.map.policy.base.AttachedPreparationMixin` provides the method
:meth:`~dockermap.map.policy.base.AttachedPreparationMixin.prepare_container` for adjusting permissions on attached
volumes.

For an implementation example, have a look at :class:`~dockermap.map.policy.simple.SimpleCreateMixin`, or the full
policy, :class:`~dockermap.map.policy.simple.SimplePolicy`.

.. _container_lazy:

Lazy resolution of variables
----------------------------
Container maps can be modified at any time, but sometimes it may be more practical to defer the initialization of
variables to a later point. For example, if you have a function
``get_path(arg1, keyword_arg1='kw1', keyword_arg2='kw2')``, you would usually assign the result directly::

    container_map.host.volume1 = get_path(arg1, keyword_arg1='kw1', keyword_arg2='kw2')

If the value is potentially not ready at the time the container map is being built, the function call can be delayed
until ``volume1`` is actually used by a container configuration. In order to set a value for lazy resolution, wrap the
function and its arguments inside :class:`dockermap.functional.lazy` or :class:`dockermap.functional.lazy_once`. The
difference between the two is that the latter stores the result and re-uses it whenever it is accessed more than once,
while the former calls the function and reproduces the current value on every use::

    from dockermap.functional import lazy
    container_map.host.volume1 = lazy(get_path, arg1, keyword_arg1='kw1', keyword_arg2='kw2')

or::

    from dockermap.functional import lazy_once
    container_map.host.volume1 = lazy_once(get_path, arg1, keyword_arg1='kw1', keyword_arg2='kw2')


Special case: serialization
"""""""""""""""""""""""""""
In case of serialization, it may not be possible to customize the behavior this way. Provided that the input values can
be represented during serialization using certain Python types, these types can be registered for pre-processing as
as well using :func:`~dockermap.functional.register_type`.

For example, if a library uses MsgPack for serializing data, you can represent a value for serialization with::

    from msgpack import ExtType

    MY_EXT_TYPE_CODE = 1
    ...
    container_map.host.volume1 = ExtType(MY_EXT_TYPE_CODE, b'info represented as bytes')

For deserialization, you could usually reconstruct your original value by writing a simple function and passing this
in ``ext_hook``::

    def my_ext_hook(code, data):
        if code == MY_EXT_TYPE_CODE:
            # This function should reconstruct the necessary information from the serailized data.
            return my_info(data)
        return ExtType(code, data)

If you do however, not have access to the loading function, you can slightly modify aforementioned function, and
register ExtType for late value resolution as well::

    from dockermap.functional import register_type

    def my_ext_hook(ext_data):
        if ext_data.code == MY_EXT_TYPE_CODE:
            return my_info(ext_data.data)
        return ext_data

    register_type(ExtType, my_ext_hook)

Note that you have to register the exact type, not a superclass of it, in order for the lookup to work.

.. _container_lazy_availability:

Availability
""""""""""""
Lazy value resolution is available at the following points:

* On container maps:

  * the main :attr:`~dockermap.map.container.ContainerMap.repository` prefix;
  * paths for all :attr:`~dockermap.map.container.ContainerMap.volumes` aliases;
  * the host volume :attr:`~dockermap.map.config.HostVolumeConfiguration.root` path;
  * and all :attr:`~dockermap.map.container.ContainerMap.host` volume paths.
* Within container configurations:

  * the :attr:`~dockermap.map.config.ContainerConfiguration.user` property;
  * host ports provided in the :attr:`~dockermap.map.config.ContainerConfiguration.exposes`, but not for the exposed
    port of the container (i.e. the first item of the tuple);
  * elements of :attr:`~dockermap.map.config.ContainerConfiguration.create_options` and
    :attr:`~dockermap.map.config.ContainerConfiguration.start_options`;
  * and elements listed in :attr:`~dockermap.map.config.ContainerConfiguration.shares`.
* On client configuration: For addresses in :attr:`~dockermap.map.config.ClientConfiguration.interfaces`.

.. _Docker-Fabric: https://pypi.python.org/pypi/docker-fabric
