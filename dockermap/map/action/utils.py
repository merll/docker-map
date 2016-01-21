# -*- coding: utf-8 -*-
from __future__ import unicode_literals


def merge_dependency_paths(item_paths):
    """
    Utility function that merges multiple dependency paths, as far as they share dependencies. Paths are evaluated
    and merged in the incoming order. Later paths that are independent, but share some dependencies, are shortened
    by these dependencies. Paths that are contained in another entirely are discarded.

    :param item_paths: List or tuple of items along with their dependency path.
    :type item_paths: list[(Any, list[Any])]
    :return: List of merged or independent paths.
    :rtype: list[(Any, list[Any])]
    """
    merged_paths = []
    for item, path in item_paths:
        sub_path_idx = None
        path_set = set(path)
        for index, (merged_item, merged_path, merged_set) in enumerate(merged_paths):
            if item in merged_set:
                path, path_set = [], set()
                break
            elif merged_item in path_set:
                sub_path_idx = index
                break
            elif merged_set & path_set:
                path = [p for p in path if p not in merged_set]
                path_set = set(path)
                if not path:
                    break
        if sub_path_idx is not None:
            merged_paths.pop(sub_path_idx)
        if path:
            merged_paths.append((item, path, path_set))
    return [(i[0], i[1]) for i in merged_paths]
