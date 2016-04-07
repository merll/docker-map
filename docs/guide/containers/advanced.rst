.. _container_advanced:

Advanced library usage
======================

Docker-Map can be used within Python applications directly, but also be used as a base implementation for other
libraries. This section covers some areas that may be relevant when implementing enhancements, like `Docker-Fabric`_.

.. _policy_implementation:

Implementing policies
---------------------
Before version 0.7.0, policies compared container maps to the current state on the Docker client, and performed changes
directly. In later versions, implementations of :class:`~dockermap.map.policy.base.BasePolicy` only define a few
guidelines, such as how containers are named, how image names are resolved, and which client objects to use:

* :meth:`~dockermap.map.policy.base.BasePolicy.get_clients` provides the clients, that a client configuration should be
  applied to;
* :meth:`~dockermap.map.policy.base.BasePolicy.get_dependencies` and
  :meth:`~dockermap.map.policy.base.BasePolicy.get_dependents` return the dependency path of
  containers for deciding in which order to create, start, stop, and remove containers;
* :meth:`~dockermap.map.policy.base.BasePolicy.get_default_client_name`,
  :meth:`~dockermap.map.policy.base.BasePolicy.cname`,
  :meth:`~dockermap.map.policy.base.BasePolicy.resolve_cname`,
  :meth:`~dockermap.map.policy.base.BasePolicy.image_name`,
  :meth:`~dockermap.map.policy.base.BasePolicy.get_hostname`, and
  :meth:`~dockermap.map.policy.base.BasePolicy.get_domainname` generate inputs for aforementioned functions. They can
  be overridden separately.

Changing behavior
-----------------
Operations are performed by a set of three components:

* So-called state generators, implementations of :class:`~dockermap.map.state.base.AbstractStateGenerator`, determine
  the current status of a container. They also establish if and in which the dependency path is being followed.
  Currently there are four implementations:

  * :class:`~dockermap.map.state.base.SingleStateGenerator` detects the basic state of a single container configuration,
    e.g. existence, running, exit code.
  * :class:`~dockermap.map.state.base.DependencyStateGenerator` is an extension of the aforementioned and used for
    forward-directed actions such as creating and starting containers, running scripts etc. It follows the dependency
    path of a container configuration, i.e. detecting states of a dependency first.
  * :class:`~dockermap.map.state.update.UpdateStateGenerator` is a more sophisticated implementation of
    :class:`~dockermap.map.state.base.DependencyStateGenerator`. In addition to the basic state it also checks for
    inconsistencies between virtual filesystems shared between containers and differences to the configuration.
  * :class:`~dockermap.map.state.base.DependentStateGenerator` also detects the basic state of containers, but follows
    the reverse dependency path and is therefore used for stopping and removing containers.

* Action generators, implementations of :class:`~dockermap.map.action.base.AbstractActionGenerator`, transform these
  states into planned client actions. There is one action generator implementation, e.g.
  :class:`~dockermap.map.action.simple.CreateActionGenerator` aims to create all containers along the detected states
  that do not exist.
* The runners perform the planned actions the client. They are implementations of
  :class:`~dockermap.map.runner.AbstractRunner` and decide how to direct the client to applying the container
  configuration, i.e. which methods and arguments to use. Currently there is only one implementation:
  :class:`~dockermap.map.runner.base.DockerClientRunner`.

The instance of :class:`~dockermap.map.client.MappingDockerClient` decides which elements to use. For each action a
pair of a state generator and action generator is configured in
:attr:`~dockermap.map.client.MappingDockerClient.generators`.
:attr:`~dockermap.map.client.MappingDockerClient.runner_class` defines which runner implementation to use.

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


Serialization issues
""""""""""""""""""""
In case of serialization, it may not be possible to customize the behavior using aforementioned lazy functions.
Provided that the input values can be represented by serializable Python types, these types can be registered for
pre-processing using :func:`~dockermap.functional.register_type`.

For example, if a library uses MsgPack for serializing data, you can represent a value for serialization with::

    from msgpack import ExtType

    MY_EXT_TYPE_CODE = 1
    ...
    container_map.host.volume1 = ExtType(MY_EXT_TYPE_CODE, b'info represented as bytes')

ExtType is supported by MsgPack's Python implementation, and therefore as long as the byte data carries all information
necessary to reproduce the actual value, no additional steps are necessary for serialization. During deserialization,
you could usually reconstruct your original value by writing a simple function and passing this in ``ext_hook``::

    def my_ext_hook(code, data):
        if code == MY_EXT_TYPE_CODE:
            # This function should reconstruct the necessary information from the serialized data.
            return my_info(data)
        return ExtType(code, data)


This is the preferred method. If you however do not have access to the loading function (e.g. because it is embedded
in another library you are using), you can slightly modify aforementioned function, and register ExtType for late value
resolution::

    from dockermap.functional import register_type

    def my_ext_hook(ext_data):
        if ext_data.code == MY_EXT_TYPE_CODE:
            return my_info(ext_data.data)
        raise ValueError("Unexpected ext type code.", ext_data.code)

    register_type(ExtType, my_ext_hook)

Note that you have to register the exact type, not a superclass of it, in order for the lookup to work.

Pre-resolving values
""""""""""""""""""""
Aforementioned type registry is limited to values as listed in :ref:`container_lazy_availability`. Additionally it may
be difficult to detect errors in the configuration beforehand. In case the data can be pre-processed at a better
time (e.g. after deserialization, in a configuration method), the method :meth:`dockermap.funcitonal.resolve_deep` can
resolve a structure of lists and dictionaries into their current values.

Rather than registering types permanently, they can also be passed to that function for temporary use, e.g.::

    from dockermap.functional import expand_type_name, resolve_deep

    # assume aforementioned example of my_ext_hook

    resolve_dict = {expand_type_name(ExtType): my_ext_hook}
    map_content = resolve_deep(deserialized_map_content, types=resolve_dict)

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
  * items of :attr:`~dockermap.map.config.ContainerConfiguration.binds`, if they are not volume aliases, i.e. they
    directly describe container volume and host path.
  * command line and user defined in each element of :attr:`~dockermap.map.config.ContainerConfiguration.exec_commands`;
  * and elements listed in :attr:`~dockermap.map.config.ContainerConfiguration.shares`.
* On client configuration: For addresses in :attr:`~dockermap.map.config.ClientConfiguration.interfaces`.

.. _Docker-Fabric: https://pypi.python.org/pypi/docker-fabric
