# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import os


expand_path = lambda value: os.path.expanduser(os.path.expandvars(value))


def parse_response(response):
    """
    Decodes the JSON response, simply ignoring syntax errors. Therefore it should be used for filtering visible output
    only.

    :param response: Server response as a JSON string.
    :type response: unicode
    :return: Decoded object from the JSON string. Returns `None` if input was invalid.
    :rtype: object
    """
    try:
        obj = json.loads(response, encoding='utf-8')
    except ValueError:
        return None
    return obj


def is_repo_image(image):
    """
    Checks whether the given image has a name, i.e. is a repository image. This does not imply that it is
    assigned to an external repository.

    :param image: Image structure from the Docker Remote API.
    :type image: dict
    :return: ``False`` if the only image name and tag is <none>, ``True`` otherwise.
    :rtype: bool
    """
    return image['RepoTags'][0] != '<none>:<none>'


def is_latest_image(image):
    """
    Checks whether the given image has any tag marked as `latest`.

    :param image: Image structure from the Docker Remote API.
    :type image: dict
    :return: ``True`` if any of the names of the current image includes the tag `latest`, ``False`` otherwise.
    :rtype: bool
    """
    return any(':latest' in tag for tag in image['RepoTags'])
