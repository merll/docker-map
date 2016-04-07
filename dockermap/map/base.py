# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
import logging

import six
import docker
from docker.errors import APIError

from .dep import SingleDependencyResolver
from ..build.context import DockerContext
from ..utils import tag_check_function, is_repo_image, parse_response

log = logging.getLogger(__name__)

LOG_PROGRESS_FORMAT = "{0} {1} {2}"
LOG_CONTAINER_FORMAT = "[%s] %s"


class DockerStatusError(Exception):
    def __init__(self, *args):
        detail = args[1]
        if isinstance(detail, dict):
            detail.pop('message', None)
            if not detail:
                args = args[:1]
        super(DockerStatusError, self).__init__(*args)

    @property
    def message(self):
        return self.args[0]

    @property
    def detail(self):
        return self.args[1] if len(self.args) > 1 else None


class ContainerImageResolver(SingleDependencyResolver):
    """
    Finds dependencies of containers on images and images on one another, where each container depends on exactly one
    image and each image depends on one or zero images. The purpose is only to find *if* images are used - not by what -
    in order to perform a clean-up.

    :param container_images: Set of image ids currently used by containers.
    :type container_images: set[unicode | str]
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
        :type item: unicode | str
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
    def _docker_log_stream(self, response, raise_on_error):
        log_str = None
        for e in response:
            output = parse_response(e)
            if 'stream' in output:
                log_str = output['stream']
                if log_str and log_str[-1] == '\n':
                    log_str = log_str[:-1]
                self.push_log(log_str, logging.INFO)
            elif 'error' in output:
                log_str = output['error']
                self.push_log(log_str, logging.ERROR)
                if raise_on_error:
                    raise DockerStatusError(log_str, output.get('errorDetail'))
        return log_str  # Last line written to stdout

    def _docker_status_stream(self, response, raise_on_error):
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
                        self.push_log(output['status'], logging.INFO)
                elif 'error' in output:
                    error_message = output['error']
                    self.push_log(error_message, logging.ERROR)
                    if raise_on_error:
                        raise DockerStatusError(error_message, output.get('errorDetail'))
        return result

    def push_progress(self, status, object_id, progress):
        """
        Handles streamed progress information.

        :param status: Status text.
        :type status: unicode | str
        :param object_id: Object that the progress is reported on.
        :type object_id: unicode | str
        :param progress: Progress bar.
        :type progress: unicode | str
        """
        pass

    def push_log(self, info, level, *args, **kwargs):
        """
        Writes logs. To be fully implemented by subclasses.

        :param info: Log message content.
        :type info: unicode | str
        :param level: Logging level.
        :type level: int
        :param args: Positional arguments to pass to logger.
        :param kwargs: Keyword arguments to pass to logger.
        """
        log.log(level, info, *args, **kwargs)

    def build(self, tag, add_latest_tag=False, add_tags=None, raise_on_error=False, **kwargs):
        """
        Overrides the superclass `build()` and filters the output. Messages are deferred to `push_log`, whereas the
        final message is checked for a success message. If the latter is found, only the new image id is returned.

        :param tag: Tag of the new image to be built. Unlike in the superclass, this is obligatory.
        :type tag: unicode | str
        :param add_latest_tag: In addition to the image ``tag``, tag the image with ``latest``.
        :type add_latest_tag: bool
        :param add_tags: Additional tags. Can also be used as an alternative to ``add_latest_tag``.
        :type add_tags: list[unicode | str]
        :param raise_on_error: Raises errors in the status output as a DockerStatusException. Otherwise only logs
         errors.
        :type raise_on_error: bool
        :param kwargs: See :meth:`docker.client.Client.build`.
        :return: New, generated image id or `None`.
        :rtype: unicode | str
        """
        response = super(DockerClientWrapper, self).build(tag=tag, **kwargs)
        # It is not the kwargs alone that decide if we get a stream, so we have to check.
        if isinstance(response, tuple):
            image_id = response[0]
        else:
            last_log = self._docker_log_stream(response, raise_on_error)
            if last_log and last_log.startswith('Successfully built '):
                image_id = last_log[19:]  # Remove prefix
            else:
                image_id = None

        if not image_id:
            return None

        repo, __, i_tag = tag.rpartition(':')
        tag_set = set(add_tags or ())
        if add_latest_tag:
            tag_set.add('latest')
        tag_set.discard(i_tag)

        if repo and tag_set:
            for t in tag_set:
                self.tag(image_id, repo, t, force=True)
        return image_id

    def login(self, username, password=None, email=None, registry=None, reauth=False, **kwargs):
        """
        Login to a Docker registry server.

        :param username: User name for login.
        :type username: unicode | str
        :param password: Login password; may be ``None`` if blank.
        :type password: unicode | str
        :param email: Optional; email address for login.
        :type email: unicode | str
        :param registry: Optional registry URL to log in to. Uses the Docker index by default.
        :type registry: unicode | str
        :param reauth: Re-authenticate, even if the login has been successful before.
        :type reauth: bool
        :param kwargs: Additional kwargs to :meth:`docker.client.Client.login`.
        :return: ``True`` if the login has succeeded, or if it has not been necessary as it succeeded before. ``False``
          otherwise.
        :rtype: bool
        """
        response = super(DockerClientWrapper, self).login(username, password, email, registry, reauth=reauth, **kwargs)
        return response.get('Status') == 'Login Succeeded' or response.get('username') == username

    def pull(self, repository, tag=None, stream=False, raise_on_error=False, **kwargs):
        """
        Pulls an image repository from the registry.

        :param repository: Name of the repository.
        :type repository: unicode | str
        :param tag: Optional tag to pull; by default pulls all tags of the given repository.
        :type tag: unicode | str
        :param stream: Use the stream output format with additional status information.
        :type stream: bool
        :param raise_on_error: Raises errors in the status output as a DockerStatusException. Otherwise only logs
         errors.
        :type raise_on_error: bool
        :param kwargs: Additional kwargs for :meth:`docker.client.Client.pull`.
        :return: ``True`` if the image has been pulled successfully.
        :rtype: bool
        """
        response = super(DockerClientWrapper, self).pull(repository, tag=tag, stream=stream, **kwargs)
        if stream:
            result = self._docker_status_stream(response, raise_on_error)
        else:
            result = self._docker_status_stream(response.split('\r\n') if response else (), raise_on_error)
        return result and not result.get('error')

    def push(self, repository, stream=False, raise_on_error=False, **kwargs):
        """
        Pushes an image repository to the registry.

        :param repository: Name of the repository (can include a tag).
        :type repository: unicode | str
        :param stream: Use the stream output format with additional status information.
        :type stream: bool
        :param raise_on_error: Raises errors in the status output as a DockerStatusException. Otherwise only logs
         errors.
        :type raise_on_error: bool
        :param kwargs: Additional kwargs for :meth:`docker.client.Client.push`.
        :return: ``True`` if the image has been pushed successfully.
        :rtype: bool
        """
        response = super(DockerClientWrapper, self).push(repository, stream=stream, **kwargs)
        if stream:
            result = self._docker_status_stream(response, raise_on_error)
        else:
            result = self._docker_status_stream(response.split('\r\n') if response else (), raise_on_error)
        return result and not result.get('error')

    def build_from_context(self, ctx, tag, **kwargs):
        """
        Builds a docker image from the given docker context with a `Dockerfile` file object.

        :param ctx: An instance of :class:`~.context.DockerContext`.
        :type ctx: dockermap.build.context.DockerContext
        :param tag: New image tag.
        :type tag: unicode | str
        :param kwargs: See :meth:`docker.client.Client.build`.
        :return: New, generated image id or `None`.
        :rtype: unicode | str
        """
        return self.build(fileobj=ctx.fileobj, tag=tag, custom_context=True, encoding=ctx.stream_encoding, **kwargs)

    def build_from_file(self, dockerfile, tag, **kwargs):
        """
        Builds a docker image from the given :class:`~dockermap.build.dockerfile.DockerFile`. Use this as a shortcut to
        :meth:`build_from_context`, if no extra data is added to the context.

        :param dockerfile: An instance of :class:`~dockermap.build.dockerfile.DockerFile`.
        :type dockerfile: dockermap.build.dockerfile.DockerFile
        :param tag: New image tag.
        :type tag: unicode | str
        :param kwargs: See :meth:`docker.client.Client.build`.
        :return: New, generated image id or ``None``.
        :rtype: unicode | str
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
                c_names = [name[1:] for name in container['Names'] or ()]
                c_status = container['Status']
                if ((include_initial and c_status == '') or c_status.startswith('Exited')) and exclude_names.isdisjoint(c_names):
                    c_id = container['Id']
                    yield c_id, c_names[0] if c_names else c_id

        for cid, cn in _stopped_containers():
            try:
                self.remove_container(cn)
            except APIError as e:
                if e.response.status_code != 404:
                    self.push_log("Could not remove container '%s': %s", logging.ERROR, cn, e.explanation)
                    if raise_on_error:
                        six.reraise(*sys.exc_info())

    def cleanup_images(self, remove_old=False, keep_tags=None, raise_on_error=False):
        """
        Finds all images that are neither used by any container nor another image, and removes them; by default does not
        remove repository images.

        :param remove_old: Also removes images that have repository names, but no `latest` tag.
        :type remove_old: bool
        :param keep_tags: List of tags to not remove.
        :type keep_tags: list[unicode | str]
        :param raise_on_error: Forward errors raised by the client and cancel the process. By default only logs errors.
        :type raise_on_error: bool
        """
        used_images = set(self.inspect_container(container['Id'])['Image']
                          for container in self.containers(all=True))
        image_dependencies = ((image['Id'], image['ParentId']) for image in self.images(all=True))
        resolver = ContainerImageResolver(used_images, image_dependencies)
        if keep_tags:
            check_tags = set(keep_tags)
            if remove_old:
                check_tags.add('latest')
            tag_check = tag_check_function(check_tags)
        elif remove_old:
            tag_check = tag_check_function(['latest'])
        else:
            tag_check = is_repo_image
        unused_images = set(image['Id'] for image in self.images()
                            if not tag_check(image) and not resolver.get_dependencies(image['Id']))
        for iid in unused_images:
            try:
                self.remove_image(iid)
            except APIError as e:
                if e.response.status_code != 404:
                    self.push_log("Could not remove image '%s': %s", logging.ERROR, iid, e.explanation)
                    if raise_on_error:
                        six.reraise(*sys.exc_info())

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
        tags = {tag: i['Id'] for i in current_images for tag in i['RepoTags']}
        return tags

    def push_container_logs(self, container):
        """
        Reads the current container logs and passes them to :meth:`~push_log`. Removes a trailing empty line and
        prefixes each log line with the container name.

        :param container: Container name or id.
        :type container: unicode | str
        """
        logs = self.logs(container).decode('utf-8')
        log_lines = logs.split('\n')
        if log_lines and not log_lines[-1]:
            log_lines.pop()
        for line in log_lines:
            self.push_log(LOG_CONTAINER_FORMAT, logging.INFO, container, line)

    def remove_container(self, container, raise_on_error=False, **kwargs):
        """
        Removes a container. For convenience optionally ignores API errors.

        :param container: Container name.
        :type container: unicode | str
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
                self.push_log("Failed to stop container '%s': %s", logging.ERROR, container, e.explanation)
                if raise_on_error:
                    six.reraise(*sys.exc_info())

    def stop(self, container, raise_on_error=False, **kwargs):
        """
        Removes a container. For convenience optionally ignores API errors.

        :param container: Container name.
        :type container: unicode | str
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
                self.push_log("Failed to stop container '%s': %s", logging.ERROR, container, e.explanation)
                if raise_on_error:
                    six.reraise(*sys.exc_info())

    def remove_all_containers(self, stop_timeout=10):
        """
        First stops (if necessary) and them removes all containers present on the Docker instance.

        :param stop_timeout: Timeout to stopping each container.
        :type stop_timeout: int
        """
        containers = [(container['Id'], container['Status'].startswith('Exited'))
                      for container in self.containers(all=True)]
        for c_id, stopped in containers:
            if not stopped:
                self.stop(c_id, timeout=stop_timeout)
        for c_id, __ in containers:
            self.remove_container(c_id)

    def copy_resource(self, container, resource, local_filename):
        """
        *Experimental:* Copies a resource from a Docker container to a local tar file. For details, see
        :meth:`docker.client.Client.copy`.

        :param container: Container name or id.
        :type container: unicode | str
        :param resource: Resource inside the container.
        :type resource: unicode | str
        :param local_filename: Local file to store resource into. Will be overwritten if present.
        :type local_filename: unicode | str
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
        :type image: unicode | str
        :param local_filename: Local file to store image into. Will be overwritten if present.
        :type local_filename: unicode | str
        """
        raw = self.get_image(image)
        with open(local_filename, 'wb+') as f:
            for buf in raw:
                f.write(buf)
