# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

import docker
from docker.errors import APIError

from .dep import SingleDependencyResolver
from ..build.context import DockerContext
from ..utils import is_latest_image, is_repo_image, parse_response


logger = logging.getLogger(__name__)
CONTAINER_LOG = logging.INFO + 2
STREAM_LOG = logging.INFO + 1
STREAM_PROGRESS = logging.INFO - 1
LOG_PROGRESS_FORMAT = "{0} {1} {2}"
LOG_CONTAINER_FORMAT = "[{0}] {1}"


class ContainerImageResolver(SingleDependencyResolver):
    """
    Finds dependencies of containers on images and images on one another, where each container depends on exactly one
    image and each image depends on one or zero images. The purpose is only to find *if* images are used - not by what -
    in order to perform a clean-up.

    :param container_images: Set of image ids currently used by containers.
    :type container_images: set[unicode]
    :param images: Iterable or dictionary of images in the format `(image, parent_image)`.
    :type images: iterable
    """

    def __init__(self, container_images=None, images=None):
        super(ContainerImageResolver, self).__init__(images)
        self._container_images = container_images

    def merge_dependency(self, item, resolve_parent, parent):
        """
        Checks if any containers depend on the current image id; if not, moves down the hierarchy, checking the parent
        images.

        :param item: Image id to check for dependent items.
        :type item: unicode
        :param resolve_parent: Function to check parent image for dependencies.
        :param parent: Parent image id.
        :return: `True` if any dependency has been found, `False` otherwise.
        :type: bool
        """
        return item in self._container_images or super(ContainerImageResolver, self).merge_dependency(item, resolve_parent, parent)


class DockerClientWrapper(docker.Client):
    """
    Adds a few utility functions to the Docker API client.
    """
    def _docker_log_stream(self, response):
        log_str = None
        for e in response:
            output = parse_response(e)
            log_str = output['stream'][:-1] if output and 'stream' in output else None
            if log_str:
                self.push_log(log_str, STREAM_LOG)
        return log_str  # Last line written to stdout

    def _docker_status_stream(self, response):
        result = {}
        for e in response:
            output = parse_response(e)
            if output:
                result.update(output)
                if 'status' in output:
                    oid = output.get('id')
                    progress = output.get('progress', '')
                    if oid:
                        self.push_progress(output['status'], oid, progress)
                    else:
                        self.push_log(output['status'], STREAM_LOG)
                elif 'error' in output:
                    self.push_log(output['error'], logging.ERROR)
        return result

    def push_progress(self, status, object_id, progress):
        """
        Handles streamed progress information.

        :param status: Status text.
        :type status: unicode
        :param object_id: Object that the progress is reported on.
        :type object_id: unicode
        :param progress: Progress bar.
        :type progress: unicode
        """
        pass

    def push_log(self, info, level=logging.INFO):
        """
        Writes logs. To be fully implemented by subclasses.

        :param info: Log message content.
        :type info: unicode
        :param level: Logging level; default is :data:`~logging.INFO`.
        :type level: int
        """
        logger.log(level, info)

    def build(self, tag, add_latest_tag=False, **kwargs):
        """
        Overrides the superclass `build()` and filters the output. Messages are deferred to `push_log`, whereas the
        final message is checked for a success message. If the latter is found, only the new image id is returned.

        :param tag: Tag of the new image to be built. Unlike in the superclass, this is obligatory.
        :type tag: unicode
        :param add_latest_tag: In addition to the image `tag`, tag the image with `latest`.
        :type add_latest_tag: bool
        :param kwargs: See :meth:`docker.client.Client.build`.
        :return: New, generated image id or `None`.
        :rtype: unicode
        """
        response = super(DockerClientWrapper, self).build(tag=tag, **kwargs)
        last_log = self._docker_log_stream(response)
        if last_log is not None and last_log.startswith('Successfully built '):
            image_id = last_log[19:]  # Remove prefix
            repo, __, i_tag = tag.partition(':')
            if i_tag and i_tag != 'latest':
                self.tag(image_id, repo, 'latest', force=True)
            return image_id
        return None

    def login(self, username, password=None, email=None, registry=None, reauth=False, **kwargs):
        """
        Login to a Docker registry server.

        :param username: User name for login.
        :type username: unicode
        :param password: Login password; may be ``None`` if blank.
        :type password: unicode
        :param email: Optional; email address for login.
        :type email: unicode
        :param registry: Optional registry URL to log in to. Uses the Docker index by default.
        :type registry: unicode
        :param reauth: Re-authenticate, even if the login has been successful before.
        :type reauth: bool
        :param kwargs: Additional kwargs to :meth:`docker.client.Client.login`.
        :return: ``True`` if the login has succeeded, or if it has not been necessary as it succeeded before. ``False``
          otherwise.
        :rtype: bool
        """
        response = super(DockerClientWrapper, self).login(username, password, email, registry, reauth=reauth, **kwargs)
        return response.get('Status') == 'Login Succeeded' or response.get('username') == username

    def pull(self, repository, tag=None, stream=False, **kwargs):
        """
        Pulls an image repository from the registry.

        :param repository: Name of the repository.
        :type repository: unicode
        :param tag: Optional tag to pull; by default pulls all tags of the given repository.
        :type tag: unicode
        :param stream: Use the stream output format with additional status information.
        :type stream: bool
        :param kwargs: Additional kwargs for :meth:`docker.client.Client.pull`.
        :return: ``True`` if the image has been pulled successfully.
        :rtype: bool
        """
        response = super(DockerClientWrapper, self).pull(repository, tag=tag, stream=stream, **kwargs)
        if stream:
            result = self._docker_status_stream(response)
        else:
            result = self._docker_status_stream(response.split('\r\n') if response else ())
        return result and not result.get('error')

    def push(self, repository, stream=False, **kwargs):
        """
        Pushes an image repository to the registry.

        :param repository: Name of the repository (can include a tag).
        :type repository: unicode
        :param stream: Use the stream output format with additional status information.
        :type stream: bool
        :param kwargs: Additional kwargs for :meth:`docker.client.Client.push`.
        :return: ``True`` if the image has been pushed successfully.
        :rtype: bool
        """
        response = super(DockerClientWrapper, self).push(repository, stream=stream, **kwargs)
        if stream:
            result = self._docker_status_stream(response)
        else:
            result = self._docker_status_stream(response.split('\r\n') if response else ())
        return result and not result.get('error')

    def build_from_context(self, ctx, tag, **kwargs):
        """
        Builds a docker image from the given docker context with a `Dockerfile` file object.

        :param ctx: An instance of :class:`~.context.DockerContext`.
        :type ctx: dockermap.build.context.DockerContext
        :param tag: New image tag.
        :type tag: unicode
        :param kwargs: See :meth:`docker.client.Client.build`.
        :return: New, generated image id or `None`.
        :rtype: unicode
        """
        return self.build(fileobj=ctx.fileobj, tag=tag, custom_context=True, encoding=ctx.stream_encoding, **kwargs)

    def build_from_file(self, dockerfile, tag, **kwargs):
        """
        Builds a docker image from the given :class:`~dockermap.build.dockerfile.DockerFile`. Use this as a shortcut to
        :meth:`build_from_context`, if no extra data is added to the context.

        :param dockerfile: An instance of :class:`~dockermap.build.dockerfile.DockerFile`.
        :type dockerfile: dockermap.build.dockerfile.DockerFile
        :param tag: New image tag.
        :type tag: unicode
        :param kwargs: See :meth:`docker.client.Client.build`.
        :return: New, generated image id or ``None``.
        :rtype: unicode
        """
        with DockerContext(dockerfile, finalize=True) as ctx:
            return self.build_from_context(ctx, tag, **kwargs)

    def cleanup_containers(self, include_initial=False, exclude=None, raise_on_error=False):
        """
        Finds all stopped containers and removes them; by default does not remove containers that have never been
        started.

        :param include_initial: Consider containers that have never been started.
        :type include_initial: bool
        :param exclude: Container names to exclude from the cleanup process.
        :type exclude: iterable
        :param raise_on_error: Forward errors raised by the client and cancel the process. By default only logs errors.
        :type raise_on_error: bool
        """
        def _stopped_containers():
            exclude_names = set(exclude or ())
            for container in self.containers(all=True):
                c_name = container['Names'][0][1:]
                c_status = container['Status']
                if ((include_initial and c_status == '') or c_status.startswith('Exited')) and c_name not in exclude_names:
                    yield container['Id'], c_name

        for cid, cn in _stopped_containers():
            try:
                self.remove_container(cid)
            except APIError as e:
                if e.response.status_code != 404:
                    self.push_log("Could not remove container '{0}': {1}".format(cn, e.explanation), logging.ERROR)
                    if raise_on_error:
                        raise e

    def cleanup_images(self, remove_old=False, raise_on_error=False):
        """
        Finds all images that are neither used by any container nor another image, and removes them; by default does not
        remove repository images.

        :param remove_old: Also removes images that have repository names, but no `latest` tag.
        :type remove_old: bool
        :param raise_on_error: Forward errors raised by the client and cancel the process. By default only logs errors.
        :type raise_on_error: bool
        """
        used_images = set(self.inspect_container(container['Id'])['Image']
                          for container in self.containers(all=True))
        image_dependencies = ((image['Id'], image['ParentId']) for image in self.images(all=True))
        resolver = ContainerImageResolver(used_images, image_dependencies)
        tag_check = is_latest_image if remove_old else is_repo_image
        unused_images = set(image['Id'] for image in self.images()
                            if not tag_check(image) and not resolver.get_dependencies(image['Id']))

        for iid in unused_images:
            try:
                self.remove_image(iid)
            except APIError as e:
                if e.response.status_code != 404:
                    self.push_log("Could not remove image '{0}': {1}".format(iid, e.explanation), logging.ERROR)
                    if raise_on_error:
                        raise e

    def get_container_names(self):
        """
        Fetches names of all present containers from Docker.

        :return: All container names.
        :rtype: set
        """
        current_containers = self.containers(all=True)
        return set(c_name[1:] for c in current_containers for c_name in c['Names'])

    def get_image_tags(self):
        """
        Fetches image labels (repository / tags) from Docker.

        :return: A dictionary, with image name and tags as the key and the image id as value.
        :rtype: dict
        """
        current_images = self.images()
        tags = dict((tag, i['Id']) for i in current_images for tag in i['RepoTags'])
        return tags

    def push_container_logs(self, container):
        """
        Reads the current container logs and passes them to :meth:`~push_log`. Removes a trailing empty line and
        prefixes each log line with the container name.

        :param container: Container name or id.
        :type container: unicode
        """
        logs = self.logs(container).decode('utf-8')
        log_lines = logs.split('\n')
        if log_lines and not log_lines[-1]:
            log_lines.pop()
        for line in log_lines:
            self.push_log(LOG_CONTAINER_FORMAT.format(container, line), CONTAINER_LOG)

    def remove_container(self, container, raise_on_error=False, **kwargs):
        """
        Removes a container. For convenience optionally ignores 404 errors.

        :param container: Container name.
        :type container: unicode
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored.
        :type raise_on_error: bool
        :param kwargs: Additional keyword args for :meth:`docker.client.Client.remove_container`.
        """
        try:
            super(DockerClientWrapper, self).remove_container(container, **kwargs)
        except APIError as e:
            if e.response.status_code != 404:
                self.push_log("Failed to stop container '{0}': {1}".format(container, e.explanation),
                              logging.ERROR)
                if raise_on_error:
                    raise e

    def stop(self, container, raise_on_error=False, **kwargs):
        """
        Removes a container. For convenience optionally ignores 404 errors.

        :param container: Container name.
        :type container: unicode
        :param raise_on_error: Errors on stop and removal may result from Docker volume problems, that do not further
          affect further actions. Such errors are always logged, but do not raise an exception unless this is set to
          ``True``. Please note that 404 errors (on non-existing containers) are always ignored.
        :type raise_on_error: bool
        :param kwargs: Additional keyword args for :meth:`docker.client.Client.stop`.
        """
        try:
            super(DockerClientWrapper, self).stop(container, **kwargs)
        except APIError as e:
            if e.response.status_code != 404:
                self.push_log("Failed to remove container '{0}': {1}".format(container, e.explanation),
                              logging.ERROR)
                if raise_on_error:
                    raise e

    def remove_all_containers(self):
        """
        First stops (if necessary) and them removes all containers present on the Docker instance.
        """
        containers = [(container['Id'], container['Status'].startswith('Exited'))
                      for container in self.containers(all=True)]
        for c_id, stopped in containers:
            if not stopped:
                try:
                    self.stop(c_id)
                except APIError as e:
                    if e.response.status_code != 404:
                        raise e
        for c_id, __ in containers:
            try:
                self.remove_container(c_id)
            except APIError as e:
                if e.response.status_code != 404:
                    raise e

    def copy_resource(self, container, resource, local_filename):
        """
        *Experimental:* Copies a resource from a Docker container to a local tar file. For details, see
        :meth:`docker.client.Client.copy`.

        :param container: Container name or id.
        :type container: unicode
        :param resource: Resource inside the container.
        :type resource: unicode
        :param local_filename: Local file to store resource into. Will be overwritten if present.
        :type local_filename: unicode
        """
        raw = self.copy(container, resource)
        with open(local_filename, 'wb+') as f:
            for buf in raw:
                f.write(buf)

    def save_image(self, image, local_filename):
        """
        *Experimental:* Copies an image from Docker to a local tar file. For details, see
        :meth:`docker.client.Client.get_image`.

        :param image: Image name or id.
        :type image: unicode
        :param local_filename: Local file to store image into. Will be overwritten if present.
        :type local_filename: unicode
        """
        raw = self.get_image(image)
        with open(local_filename, 'wb+') as f:
            for buf in raw:
                f.write(buf)
