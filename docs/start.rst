.. _getting_started:

===============
Getting started
===============
Simple Dockerfile
-----------------
For deriving a new image from an existing `ubuntu` base image, you can use the following code::

    client = DockerClientWrapper('unix://var/run/docker.sock')
    with DockerFile('ubuntu:latest') as df:
        df.run('apt-get update')
        df.run('apt-get -y upgrade')
        client.build_from_file(df, 'new_base_image', add_latest_tag=True, rm=True)


Docker image with files
-----------------------
For adding files during the build process, use the :func:`~dockermap.build.dockerfile.DockerFile.add_file` function.
It inserts the `ADD` command into the Dockerfile, but also makes sure that file is part of the context tarball::

    client = DockerClientWrapper('unix://var/run/docker.sock')
    with DockerFile('ubuntu:latest') as df:
        df.add_file('/home/user/myfiles', '/var/lib/myfiles')
        client.build_from_file(df, 'new_image')


Removing all containers
-----------------------
The :class:`~dockermap.map.base.DockerClientWrapper` has enhances some of the default functionality of `docker-py` and
adds utility functions. For example, you can remove all stopped containers from your development machine by running::

    client = DockerClientWrapper('unix://var/run/docker.sock')
    client.cleanup_containers()


Configuring containers
----------------------
A :class:`~dockermap.map.container.ContainerMap` provides a structure for mapping out container instances along with
their dependencies.

A simple example could be a web server an an application server, where the web server uses Unix sockets for
communicating with the application server. The map could look like this::

    container_map = ContainerMap('main', {
        'nginx': { # Configure container creation and startup
            'image': 'nginx',
            'binds': {'nginx_config': 'ro'},
            'uses': 'uwsgi_socket',
            'attaches': 'nginx_log',
            'start_options': {
                'port_bindings': {80: 80, 443: 443},
            },
        },
        'uwsgi': {
            'binds': (
                {'uwsgi_config': 'ro'},
                {'app_config': 'ro'},
                'app_data',
            ),
            'attaches': ('uwsgi_log', 'app_log', 'uwsgi_socket'),
            'user': 2000,
            'permissions': 'u=rwX,g=rX,o=',
        },
        'volumes': { # Configure volume paths inside containers
            'nginx_config': '/etc/nginx',
            'nginx_log': '/var/log/nginx',
            'uwsgi_config': '/etc/uwsgi',
            'uwsgi_socket': '/var/lib/uwsgi/socket',
            'uwsgi_log': '/var/log/uwsgi',
            'app_config': '/var/lib/app/config',
            'app_log': '/var/lib/app/log',
            'app_data': '/var/lib/app/data',
        },
        'host': { # Configure volume paths on the Docker host
            'nginx_config': '/var/lib/site/config/nginx',
            'uwsgi_config': '/var/lib/site/config/uwsgi',
            'app_config': '/var/lib/site/config/app',
            'app_data': '/var/lib/site/data/app',
        },
    })


*Notes*:

* By default an instantiation of such a map performs a brief integrity check, whether all aliases as used in container
  configurations have been defined in `host` and `volumes` assignments.
* `Attached` volumes are Docker containers based on a minimal launchable image, that are created for the sole
  purpose of sharing a volume. In this example, the `nginx` container will have access to `uwsgi_socket`, but none
  of the other shared volumes.
* The aforementioned `permissions` in the `uwsgi` container assume that the working user in the `nginx` container is
  part of a group with the id `2000`. If this is not the case, you have to open up `permissions`, e.g. to
  ``u=rwX,g=rX,o=rX``.
* Although it is out of scope of this introduction, the recommended method for configuring container maps is YAML files,
  since it is syntactically simpler than Python code.

This map can be used with a :class:`~dockermap.map.client.MappingDockerClient`::

    map_client = MappingDockerClient(container_map, DockerClientWrapper('unix://var/run/docker.sock'))
    map_client.create('nginx')
    map_client.start('nginx')


This performs the following tasks:

* Resolve dependencies in order to determine which containers to start prior to `nginx`. In this case, `nginx` needs
  access to some `uwsgi_socket` volume. The latter is provided by starting `uwsgi`.
* Create containers for sharing attached volumes, and assign configured user (`chown`) and access permissions
  (`chmod`).
* Create and start containers `uwsgi` and `nginx` in that order, passing the necessary parameters to `docker-py`.
