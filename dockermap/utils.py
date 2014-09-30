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
    return image['RepoTags'][0] != '<none>:<none>'


def is_latest_image(image):
    return any(':latest' in tag for tag in image['RepoTags'])
