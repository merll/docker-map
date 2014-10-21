.. _container_yaml:

Container configurations in YAML
================================

YAML (YAML Ain’t Markup Language) files are often easier to write than Python dictionaries, and provide a good
possibility to separate code from configuration. Container maps can be maintained in and loaded from YAML files. As the
contents are imported as a dictionary, the inner structure is identical to the Python dictionary representation.

YAML elements
-------------
When used according to the full specification, YAML is a very feature-rich and powerful language. This is only
a quick introduction to the syntactical elements of YAML, as relevant for container maps:

* YAML elements can be structured in a hierarchy, similar to other markup languages. Just Like in Python, the
  hierarchy level is defined by outline indentation.
* Every line without any prefix is a key-value pair ``key: value``, and read as items of an
  associative array (a dictionary in Python). An indented key indicates a nested structure.
* Lines prefixed with a dash ``-`` followed by a space represent items of a list.
* Most data types are implicit. For example, you do not need to quote strings, unless they consist of only numbers and
  a dot and therefore could be read as integer or float. In doubt (e.g. for version numbers), you should quote them
  or prefix with the tag ``!!str``.
* Strings are trimmed (unless within quotes); in a dictionary for example, it does not matter how much space there is
  between the key and the value.
* Lists and dictionaries can also be written in inline-syle, similar to JSON syntax: Curly brackets represent a
  associative array (dictionary), square brackets a list.

For a more comprehensive reference, the Wikipedia_ article provides a good overview. The `YAML specification`_
also has detailed examples. There is also a `type list`_, which decribes most important data types.

Example
^^^^^^^

The :ref:`container_map_example` map can be more easily written as:

.. code-block:: yaml

   repository: registry.example.com
   host_root: /var/lib/site
   web_server:
     image: nginx
     binds: {web_config: ro}
     uses: app_server_socket
     attaches: web_log
     start_options:
     port_bindings: {80: 80, 443: 443}
   app_server:
     image: app
     instances:
     - instance1
     - instance2
     binds:
     - app_config: ro
     - app_data:
     attaches:
     - app_log
     - app_server_socket
     user: 2000
     permissions: u=rwX,g=rX,o=
   volumes:
     web_config: /etc/nginx
     web_log: /var/log/nginx
     app_server_socket: /var/lib/app/socket
     app_config: /var/lib/app/config
     app_log: /var/lib/app/log
     app_data: /var/lib/app/data
   host:
     web_config: config/nginx
     app_config:
       instance1: config/app1
       instance2: config/app2
     app_data:
       instance1: data/app1
       instance2: data/app2


Importing YAML maps
-------------------
The easiest way to generate a :class:`~dockermap.map.container.ContainerMap` from a YAML file is
:func:`~dockermap.map.yaml.load_map_file`::

    from dockermap.map import yaml
    map = yaml.load_map_file('/path/to/example_map.yaml')


By default the map will be named according to a ``name`` element on the root level of the map; this can be overwritten,
e.g.::

    map = yaml.load_map_file('/path/to/example_map.yaml', 'apps')

The initial integrity check can be skipped by passing ``check_integrity=False``.

If your YAML structure is not a file, but a stream, you can use :func:`~dockermap.map.yaml.load_map`. It takes a buffer
as first argument; additional arguments are identical to ``load_map_file``.

There are in total three ways to assign a name to a map, in the following order of priority:

1. The name passed as a keyword argument in :func:`~dockermap.map.yaml.load_map_file` or
   :func:`~dockermap.map.yaml.load_map`.
2. The base file name without extension from :func:`~dockermap.map.yaml.load_map_file`, if an empty string is passed
   as the ``name`` argument.
3. An extra ``name`` element on the root level of the map.


User and environment variables
------------------------------
As YAML allows for definition of custom tags, ``!path`` has been added for indicating variables that are supposed to
be expanded upon import. This is done using ``os.path.expandvars`` and ``os.path.expanduser`` (in that order). The
aforementioned example's ``host_root`` entry also could also be defined as:

.. code-block:: yaml

   host_root: !path $SITE_ROOT


Nested elements are also expanded on their first level of sub-elements, when the tag is applied to a list or
associative array:

.. code-block:: yaml

   host: !path
     web_config: $CONFIG_PATH/nginx
     app_config: !path
       instance1: $CONFIG_PATH/app1
       instance2: $CONFIG_PATH/app2


.. _Wikipedia: http://en.wikipedia.org/wiki/YAML
.. _YAML specification: http://www.yaml.org/spec/1.2/spec.html
.. _type list: http://yaml.org/type/index.html
