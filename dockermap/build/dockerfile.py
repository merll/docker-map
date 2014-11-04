# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import os
import posixpath
import six
import tarfile

from .buffer import DockerStringBuffer
from .. import DEFAULT_BASEIMAGE


def prepare_path(path, replace_space, replace_sep, expandvars, expanduser):
    """
    Performs `os.path` replacement operations on a path string.

    :param path: Path string
    :type path: unicode
    :param replace_space: Mask spaces with backslash.
    :param replace_sep: Replace potentially different path separators with POSIX path notation (use :const:`posixpath.sep`).
    :type replace_sep: bool
    :param expandvars: Expand environment variables (:func:`~os.path.expandvars`).
    :type expandvars: bool
    :param expanduser: Expand user variables (:func:`~os.path.expanduser`).
    :type expanduser: bool
    :return: Path string from `path` with aforementioned replacements.
    :rtype: unicode
    """
    r_path = path
    if expandvars:
        r_path = os.path.expandvars(r_path)
    if expanduser:
        r_path = os.path.expanduser(r_path)
    if replace_sep and os.sep != posixpath.sep:
        r_path = r_path.replace(os.path.sep, posixpath.sep)
    if replace_space:
        r_path = r_path.replace(' ', '\\ ')
    return r_path


def format_command(cmd, shell=False):
    """
    Converts a command line to the notation as used in a Dockerfile ``CMD`` and ``ENTRYPOINT`` command. In shell
    notation, this returns a simple string, whereas by default it returns a JSON-list format with the command and
    arguments.

    :param cmd: Command line as a string or tuple.
    :type cmd: unicode, string, or tuple
    :param shell: Use the notation so that Docker runs the command in a shell. Default is ``False``.
    :type shell: bool
    :return: The command string.
    :rtype: unicode
    """

    def _split_cmd():
        line = None
        for part in cmd.split(' '):
            line = part if line is None else ' '.join((line, part))
            if part[-1] != '\\':
                yield line
                line = None
        if line is not None:
            yield line

    if cmd in ([], ''):
        return '[]'
    if shell:
        if isinstance(cmd, (list, tuple)):
            return ' '.join(cmd)
        elif isinstance(cmd, six.string_types):
            return cmd
    else:
        if isinstance(cmd, (list, tuple)):
            return json.dumps(cmd, encoding='utf-8')
        elif isinstance(cmd, six.string_types):
            return json.dumps([c for c in _split_cmd()], encoding='utf-8')
    raise ValueError("Invalid type of command string or sequence: {0}".format(cmd))


def format_expose(expose):
    """
    Converts a port number or multiple port numbers, as used in the Dockerfile ``EXPOSE`` command, to a tuple.

    :param: Port numbers, can be as integer, string, or a list/tuple of those.
    :type expose: int, unicode, list, or tuple
    :return: A tuple, to be separated by spaces before inserting in a Dockerfile.
    :rtype: tuple
    """
    if isinstance(expose, (list, tuple)):
        return map(six.text_type, expose)
    elif isinstance(expose, six.string_types):
        return expose,
    return six.text_type(expose),


class DockerFile(DockerStringBuffer):
    """
    Class for constructing Dockerfiles; can be saved or used in a :class:`DockerContext`. For :class:`DockerContext`, it
    keeps track of ``ADD`` operations, so that all files can easily be added to the context tarball.

    :param name: Descriptive name to print in the Dockerfile, for documentation purposes only.
    :type name: unicode
    :param version: Version number to print in the Dockerfile comments, for documentation purposes only.
    :type version: unicode
    :param baseimage: Base image to use for the new image. Set this to ``None`` if you want to explicitly write out the
     ``FROM`` Dockerfile command.
    :type baseimage: unicode
    :param maintainer: Optional maintainer, to be used for the ``MAINTAINER`` Dockerfile command.
    :type maintainer: unicode
    :param initial: Optional initial Dockerfile contents. Should only include header comments, ``FROM``, or
     ``MAINTAINER``, if those are not set in aforementioned parameters.
    :type initial: unicode
    """
    def __init__(self, baseimage=DEFAULT_BASEIMAGE, maintainer=None, initial=None):
        super(DockerFile, self).__init__()
        self._files = []
        self._remove_files = []
        self._archives = []
        self._volumes = None
        self._entrypoint = None
        self._command = None
        self._command_shell = False
        self._cmd_user = None
        self._expose = None

        if baseimage:
            self.prefix('FROM', baseimage)
        self.blank()
        if maintainer:
            self.prefix('MAINTAINER', maintainer)
            self.blank()

        if isinstance(initial, (tuple, list)):
            self.writelines(initial)
        elif initial is not None:
            self.writeline(initial)

    def prefix(self, prefix='#', *args):
        """
        Prefix one or multiple arguments with a Dockerfile command. The default is ``#``, for comments. Multiple args will
        be separated by a space.

        :param prefix: Dockerfile command to use, e.g. ``ENV`` or ``RUN``.
        :type prefix: unicode
        :param args: Arguments to be prefixed.
        """
        self.writeline(' '.join((prefix, ) + args))

    def prefix_all(self, prefix='#', *lines):
        """
        Same as :func:`~prefix`, for multiple lines.

        :param prefix: Dockerfile command to use, e.g. ``ENV`` or ``RUN``.
        :type prefix: unicode
        :param lines: Lines with arguments to be prefixed.
        :type lines: iterable
        """
        for line in lines:
            if isinstance(line, (tuple, list)):
                self.prefix(prefix, *line)
            elif line:
                self.prefix(prefix, line)
            else:
                self.blank()

    def run(self, *args):
        """
        Insert a `RUN` command in a Dockerfile, with arguments.

        :param args: Command to be inserted after `RUN`.
        """
        self.prefix('RUN', *args)

    def run_all(self, *lines):
        """
        Insert a series of commands in a Dockerfile, all prefixed with ``RUN``.

        :param lines: Command lines to be inserted.
        :type: iterable
        """
        self.prefix_all('RUN', *lines)

    def add_file(self, src_path, dst_path=None, ctx_path=None, replace_space=True, expandvars=False, expanduser=False,
                 remove_final=False):
        """
        Adds a file to the Docker build. An ``ADD`` command is inserted, and the path is stored for later packaging of
        the context tarball.

        :param src_path: Path to the file or directory.
        :type src_path: unicode
        :param dst_path: Destination path during the Docker build. By default uses the last element of `src_path`.
        :type dst_path: unicode
        :param ctx_path: Path inside the context tarball. Can be set in order to avoid name clashes. By default
         identical to the destination path.
        :type ctx_path: unicode
        :param replace_space: Mask spaces in path names with a backslash. Default is ``True``.
        :type replace_space: bool
        :param expandvars: Expand local environment variables. Default is ``False``.
        :type expandvars: bool
        :param expanduser: Expand local user variables. Default is ``False``.
        :type expanduser: bool
        :param remove_final: Remove the file after the build operation has completed. Can be useful e.g. for source code
         archives, which are no longer needed after building the binaries. Note that this will delete recursively, so
         use with care.
        :type remove_final: bool
        """
        if dst_path is None:
            head, tail = os.path.split(src_path)
            if not tail:
                # On trailing backslashes.
                tail = os.path.split(head)[1]
                if not tail:
                    ValueError("Could not generate target path from input '{0}'; needs to be specified explicitly.")
            target_path = tail
        else:
            target_path = dst_path

        source_path = prepare_path(src_path, False, False, expandvars, expanduser)
        target_path = prepare_path(target_path, replace_space, True, expandvars, expanduser)
        if ctx_path:
            context_path = prepare_path(ctx_path, replace_space, True, expandvars, expanduser)
        else:
            context_path = target_path
        self.prefix('ADD', context_path, target_path)
        self._files.append((source_path, context_path))
        if remove_final:
            self._remove_files.append(target_path)

    def add_archive(self, src_file, remove_final=False):
        """
        Adds the contents of another tarfile to the build. It will be repackaged during context generation, and added
        to the root level of the file system. Therefore, it is not required that tar (or compression utilities) is
        present in the base image.

        :param src_file: Tar archive to add.
        :type src_file: unicode
        :param remove_final: Remove the contents after the build operation has completed. Note that this will remove all
         top-level components of the tar archive recursively. Therefore, you should not use this on standard unix
         folders.
        :type remove_final: bool
        """
        with tarfile.open(src_file, 'r') as tf:
            for member in tf.getmembers():
                if not posixpath.sep in member.name:
                    self.prefix('ADD', member.name, member.name)
                    if remove_final:
                        self._remove_files.append(member.name)
        self._archives.append(src_file)

    def add_volume(self, path):
        """
        Add a shared volume (i.e. with the ``VOLUME`` command). Not actually written until finalized.

        :param path: Path to the shared volume.
        """
        self.check_not_finalized()
        if self.volumes is None:
            self.volumes = [path]
        else:
            self.volumes.append(path)

    def comment(self, input_str=None):
        """
        Adds a comment to the Dockerfile. If not defined, adds an empty comment line.

        :param input_str: Comment.
        :type input_str: unicode
        """
        if input_str:
            self.prefix('#', input_str)
        else:
            self.write('#\n')

    def blank(self):
        """
        Adds a blank line to the Dockerfile.
        """
        self.write('\n')

    def write(self, input_str):
        """
        Adds content to the Dockerfile.

        :param input_str: Content.
        :type input_str: unicode
        """
        self.check_not_finalized()
        self.fileobj.write(input_str)

    def writelines(self, sequence):
        """
        Adds a sequence of content to the Dockerfile.

        :param sequence: Content sequence.
        :type sequence: iterable
        """
        for s in sequence:
            self.writeline(s)

    def writeline(self, input_str):
        self.check_not_finalized()
        self.fileobj.write(input_str)
        self.fileobj.write('\n')

    @property
    def volumes(self):
        """
        Returns the currently-set list of shared volumes.

        :return: Shared volumes.
        :rtype: list
        """
        return self._volumes

    @volumes.setter
    def volumes(self, value):
        """
        Sets the list of shared volumes to be set in the Dockerfile ``VOLUME`` command. Not written before finalization.

        :param value: List of shared volumes
        :type value: list
        """
        self.check_not_finalized()
        self._volumes = value

    @property
    def entrypoint(self):
        """
        Returns the currently-set entry point of the Dockerfile.

        :return: Entry point.
        :rtype: unicode, list, or tuple
        """
        return self._entrypoint

    @entrypoint.setter
    def entrypoint(self, value):
        """
        Sets the entry point for the Dockerfile ``ENTRYPOINT`` command. Not written before finalization.

        :param value: Entry point.
        :type value: unicode, list, or tuple
        """
        self.check_not_finalized()
        self._entrypoint = value

    @property
    def command(self):
        """
        Returns the currently-set default command of the Dockerfile.

        :return: Command.
        :rtype: unicode, list, or tuple
        """
        return self._command

    @command.setter
    def command(self, value):
        """
        Sets the default command for the Dockerfile ``CMD`` command. Not written before finalization.

        :param value: Command.
        :type value: unicode, list, or tuple
        """
        self.check_not_finalized()
        self._command = value

    @property
    def command_shell(self):
        """
        Returns if entry point and command should be formatted as a shell, or as an exec command upon finalization.

        :return: ``True``, if Docker should use a shell, ``False`` if exec is used.
        :rtype: bool
        """
        return self._command_shell

    @command_shell.setter
    def command_shell(self, value):
        """
        Sets if entry point and command should be formatted as a shell, or as an exec command upon finalization.

        :param value: Set to ``True``, if Docker should use a shell, use ``False`` if exec is to be used.
        :type value: bool
        """
        self.check_not_finalized()
        self._command_shell = value

    @property
    def command_user(self):
        """
        Returns the default user that should be used for the default entry point and command.

        :return: Default user name or id.
        :rtype: unicode
        """
        return self._cmd_user

    @command_user.setter
    def command_user(self, value):
        """
        Sets the default user that should be used for the default entry point and command. Upon finalization, this will
        insert a ``USER`` command right before ``ENTRYPONT`` or ``COMMAND`` if applicable. For applying this to ``RUN``
        commands, insert the ``USER`` command manually.

        :param value: User name or id. Must be valid in the docker image.
        :type value: unicode
        """
        self.check_not_finalized()
        self._cmd_user = value

    @property
    def expose(self):
        """
        Returns the ports to be inserted with the ``EXPOSE`` command in the Dockerfile.

        :return: Ports.
        :rtype: unicode, int, tuple, or list
        """
        return self._expose

    @expose.setter
    def expose(self, value):
        """
        Sets the ports to be inserted with the ``EXPOSE`` command in the Dockerfile. Not written before finalization.

        :param value: Ports.
        :return: unicode, int, tuple, or list
        """
        self.check_not_finalized()
        self._expose = value

    def finalize(self):
        """
        Finalizes the Dockerfile. Before the buffer is practically marked as read-only, the following Dockerfile
        commands are written: `RUN rm -R` on each files marked for automatic removal; ``VOLUME`` for shared volumes;
        `USER` as the default user for following commands; ``ENTRYPOINT`` and ``CMD``, each formatted as a shell or exec
        command according to :attr:`command_shell`; and ``EXPOSE`` for exposed ports.

        An attempt to finalize an already-finalized instance has no effect.
        """
        if self._finalized:
            return
        if self._remove_files:
            for filename in self._remove_files:
                self.prefix('RUN', 'rm -R', filename)
            self.blank()
        if self._volumes is not None:
            self.prefix('VOLUME', json.dumps(self._volumes, encoding='utf-8'))
        if self._cmd_user:
            self.prefix('USER', self._cmd_user)
        if self._entrypoint is not None:
            self.prefix('ENTRYPOINT', format_command(self._entrypoint, self._command_shell))
        if self._command is not None:
            self.prefix('CMD', format_command(self._command, self._command_shell))
        if self._expose is not None:
            self.prefix('EXPOSE', *format_expose(self._expose))
        super(DockerFile, self).finalize()
