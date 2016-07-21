# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import sys
import logging

import six
import docker
from docker.errors import APIError

from .docker_util import DockerUtilityMixin

log = logging.getLogger(__name__)

LOG_PROGRESS_FORMAT = "{0} {1} {2}"
LOG_CONTAINER_FORMAT = "[%s] %s"


def parse_response(response):
    """
    Decodes the JSON response, simply ignoring syntax errors. Therefore it should be used for filtering visible output
    only.

    :param response: Server response as a JSON string.
    :type response: unicode | str
    :return: Decoded object from the JSON string. Returns an empty dictionary if input was invalid.
    :rtype: dict
    """
    if isinstance(response, six.binary_type):
        response = response.decode('utf-8')
    try:
        obj = json.loads(response)
    except ValueError:
        return {}
    return obj


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


class DockerClientWrapper(DockerUtilityMixin, docker.Client):
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

        self.add_extra_tags(image_id, tag, add_tags, add_latest_tag)
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

        :param container: Container name or id.
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
                self.push_log("Failed to remove container '%s': %s", logging.ERROR, container, e.explanation)
                if raise_on_error:
                    six.reraise(*sys.exc_info())

    def remove_image(self, image, raise_on_error=False, **kwargs):
        """
        Removes a container. For convenience optionally ignores API errors.

        :param image: Image name or id.
        :type image: unicode | str
        :param raise_on_error: Errors on image removal may not further affect further actions. Such errors are always
          logged, but do not raise an exception unless this is set to ``True``. Please note that 404 errors (on
          non-existing images) are always ignored.
        :param kwargs: Additional keyword args for :meth:`docker.client.Client.remove_image`.
        """
        try:
            super(DockerClientWrapper, self).remove_image(image, **kwargs)
        except APIError as e:
            if e.response.status_code != 404:
                self.push_log("Failed to remove image '%s': %s", logging.ERROR, image, e.explanation)
                if raise_on_error:
                    six.reraise(*sys.exc_info())

    def stop(self, container, raise_on_error=False, **kwargs):
        """
        Stops a container. For convenience optionally ignores API errors.

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
