# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

import sys

from distutils.version import StrictVersion
from requests import Timeout

from ..build.context import DockerContext
from ..dep import ImageDependentsResolver
from ..exceptions import PartialResultsError


DEPRECATED_FORCE_TAG_VERSION = StrictVersion(str('1.24'))

log = logging.getLogger(__name__)


def is_repo_image(image):
    """
    Checks whether the given image has a name, i.e. is a repository image. This does not imply that it is
    assigned to an external repository.

    :param image: Image structure from the Docker Remote API.
    :type image: dict
    :return: ``False`` if the only image name and tag is <none>, or if there is no tag at all, ``True`` otherwise.
    :rtype: bool
    """
    repo_tags = image['RepoTags']
    if not repo_tags:
        return False
    return repo_tags[0] != '<none>:<none>'


def tag_check_function(tags):
    """
    Generates a function that checks whether the given image has any of the listed tags.

    :param tags: Tags to check for.
    :type tags: list[unicode | str] | set[unicode | str]
    :return: Function that returns ``True`` if any of the given tags apply to the image, ``False`` otherwise.
    :rtype: (unicode | str) -> bool
    """
    suffixes = [':{0}'.format(t) for t in tags]

    def _check_image(image):
        repo_tags = image['RepoTags']
        if not repo_tags:
            return False
        return any(r_tag.endswith(s) for s in suffixes for r_tag in repo_tags)

    return _check_image


def primary_container_name(names, default=None, strip_trailing_slash=True):
    """
    From the list of names, finds the primary name of the container. Returns the defined default value (e.g. the
    container id or ``None``) in case it cannot find any.

    :param names: List with name and aliases of the container.
    :type names: list[unicode | str]
    :param default: Default value.
    :param strip_trailing_slash: As read directly from the Docker service, every container name includes a trailing
     slash. Set this to ``False`` if it is already removed.
    :type strip_trailing_slash: bool
    :return: Primary name of the container.
    :rtype: unicode | str
    """
    if strip_trailing_slash:
        ex_names = [name[1:] for name in names if name.find('/', 2) == -1]
    else:
        ex_names = [name for name in names if name.find('/', 2) == -1]
    if ex_names:
        return ex_names[0]
    return default


class DockerUtilityMixin(object):
    def add_extra_tags(self, image_id, main_tag, extra_tags, add_latest):
        """
        Adds extra tags to an image after de-duplicating tag names.

        :param image_id: Id of the image.
        :type image_id: unicode | str
        :param main_tag: Repo / tag specification that has been used to build the image. If present, the tag will be
         removed from further arguments.
        :type main_tag: unicode | str
        :param extra_tags: Additional tags to add to the image.
        :type extra_tags: list | tuple | set | NoneType
        :param add_latest: Whether to add a ``latest`` tag to the image.
        :type add_latest: bool
        """
        repo, __, i_tag = main_tag.rpartition(':')
        tag_set = set(extra_tags or ())
        if add_latest:
            tag_set.add('latest')
        tag_set.discard(i_tag)
        added_tags = []
        tag_kwargs = {}
        if str(self.api_version) < DEPRECATED_FORCE_TAG_VERSION:
            tag_kwargs['force'] = True
        if repo and tag_set:
            for t in tag_set:
                try:
                    self.tag(image_id, repo, t, **tag_kwargs)
                except:
                    exc_info = sys.exc_info()
                    raise PartialResultsError(exc_info, added_tags)
                else:
                    added_tags.append(t)
        return added_tags

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

    def cleanup_containers(self, include_initial=False, exclude=None, raise_on_error=False, list_only=False):
        """
        Finds all stopped containers and removes them; by default does not remove containers that have never been
        started.

        :param include_initial: Consider containers that have never been started.
        :type include_initial: bool
        :param exclude: Container names to exclude from the cleanup process.
        :type exclude: collections.Iterable[unicode | str]
        :param raise_on_error: Forward errors raised by the client and cancel the process. By default only logs errors.
        :type raise_on_error: bool
        :param list_only: When set to ``True``, only lists containers, but does not actually remove them.
        :type list_only: bool
        :return: List of removed containers.
        :rtype: list[unicode | str]
        """
        exclude_names = set(exclude or ())

        def _stopped_containers():
            for container in self.containers(all=True):
                c_names = [name[1:] for name in container['Names'] or () if name.find('/', 2)]
                c_status = container['Status']
                if (((include_initial and c_status == '') or c_status.startswith('Exited') or c_status == 'Dead') and
                        exclude_names.isdisjoint(c_names)):
                    c_id = container['Id']
                    c_name = primary_container_name(c_names, default=c_id, strip_trailing_slash=False)
                    yield c_id, c_name

        stopped_containers = list(_stopped_containers())
        if list_only:
            return stopped_containers
        removed_containers = []
        for cid, cn in stopped_containers:
            try:
                self.remove_container(cn)
            except:
                exc_info = sys.exc_info()
                if raise_on_error:
                    raise PartialResultsError(exc_info, removed_containers)
            else:
                removed_containers.append(cn)
        return removed_containers

    def cleanup_images(self, remove_old=False, keep_tags=None, force=False, raise_on_error=False, list_only=False):
        """
        Finds all images that are neither used by any container nor another image, and removes them; by default does not
        remove repository images.

        :param remove_old: Also removes images that have repository names, but no `latest` tag.
        :type remove_old: bool
        :param keep_tags: List of tags to not remove.
        :type keep_tags: list[unicode | str]
        :param force: If an image is referenced by multiple repositories, Docker by default will not remove the image.
          Setting this to ``True`` forces the removal.
        :type force: bool
        :param raise_on_error: Forward errors raised by the client and cancel the process. By default only logs errors.
        :type raise_on_error: bool
        :param list_only: When set to ``True`` only lists images, but does not actually remove them.
        :type list_only: bool
        :return: List of removed image ids.
        :rtype: list[unicode | str]
        """
        used_images = set(self.inspect_container(container['Id'])['Image']
                          for container in self.containers(all=True))
        all_images = self.images(all=True)
        image_dependencies = [(image['Id'], image['ParentId'])
                              for image in all_images
                              if image['ParentId']]
        if remove_old:
            check_tags = {'latest'}
            if keep_tags:
                check_tags.update(keep_tags)
            tag_check = tag_check_function(check_tags)
        elif remove_old:
            tag_check = tag_check_function(['latest'])
        else:
            tag_check = is_repo_image
        keep_images = {image['Id']
                       for image in all_images
                       if tag_check(image)} | used_images
        test_images = [image['Id']
                       for image in all_images
                       if image['Id'] not in keep_images]
        resolver = ImageDependentsResolver(image_dependencies)
        unused_images = [image_id
                         for image_id in test_images
                         if keep_images.isdisjoint(resolver.get_dependencies(image_id))]
        if list_only:
            return unused_images
        removed_images = []
        for iid in unused_images:
            try:
                self.remove_image(iid, force=force)
            except:
                exc_info = sys.exc_info()
                if raise_on_error:
                    raise PartialResultsError(exc_info, removed_images)
            else:
                removed_images.append(iid)
        return removed_images

    def remove_all_containers(self, stop_timeout=10, list_only=False):
        """
        First stops (if necessary) and them removes all containers present on the Docker instance.

        :param stop_timeout: Timeout to stopping each container.
        :type stop_timeout: int
        :param list_only: When set to ``True`` only lists containers, but does not actually stop or remove them.
        :type list_only: bool
        :return: A tuple of two lists: Stopped container ids, and removed container ids.
        :rtype: (list[unicode | str], list[unicode | str])
        """
        containers = [(container['Id'], container['Status'])
                      for container in self.containers(all=True)]
        running_containers = [c_id
                              for c_id, status in containers
                              if not (status.startswith('Exited') or status == 'Dead')]
        if list_only:
            return running_containers, [c[0] for c in containers]
        stopped_containers = []
        for c_id in running_containers:
            try:
                self.stop(c_id, timeout=stop_timeout)
            except Timeout:
                log.warning("Container %s did not stop in time - sent SIGKILL.", c_id)
                try:
                    self.wait(c_id, timeout=stop_timeout)
                except Timeout:
                    pass
            except:
                exc_info = sys.exc_info()
                raise PartialResultsError(exc_info, (stopped_containers, []))
            else:
                stopped_containers.append(c_id)
        removed_containers = []
        for c_id, __ in containers:
            try:
                self.remove_container(c_id)
            except:
                exc_info = sys.exc_info()
                raise PartialResultsError(exc_info, (stopped_containers, removed_containers))
            else:
                removed_containers.append(c_id)
        return stopped_containers, removed_containers

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
