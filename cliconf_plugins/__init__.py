#
# (c) 2017 Red Hat Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import signal

from abc import ABCMeta, abstractmethod
from functools import wraps

from ansible.errors import AnsibleError, AnsibleConnectionFailure
from ansible.module_utils._text import to_bytes, to_text
from ansible.module_utils.six import with_metaclass

try:
    from scp import SCPClient
    HAS_SCP = True
except ImportError:
    HAS_SCP = False

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


def enable_mode(func):
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        prompt = self.connection.get_prompt()
        if not to_text(prompt, errors='surrogate_or_strict').strip().endswith('#'):
            raise AnsibleError('operation requires privilege escalation')
        return func(self, *args, **kwargs)
    return wrapped


class CliconfBase(with_metaclass(ABCMeta, object)):
    """
    A base class for implementing cli connections

    .. note:: Unlike most of Ansible, nearly all strings in
        :class:`CliconfBase` plugins are byte strings.  This is because of
        how close to the underlying platform these plugins operate.  Remember
        to mark literal strings as byte string (``b"string"``) and to use
        :func:`~ansible.module_utils._text.to_bytes` and
        :func:`~ansible.module_utils._text.to_text` to avoid unexpected
        problems.

    List of supported rpc's:
        :get_config: Retrieves the specified configuration from the device
        :edit_config: Loads the specified commands into the remote device
        :get: Execute specified command on remote device
        :get_capabilities: Retrieves device information and supported rpc methods
        :commit: Load configuration from candidate to running
        :discard_changes: Discard changes to candidate datastore

    Note: List of supported rpc's for remote device can be extracted from
          output of get_capabilities()

    :returns: Returns output received from remote device as byte string

            Usage:
            from ansible.module_utils.connection import Connection

            conn = Connection()
            conn.get('show lldp neighbors detail'')
            conn.get_config('running')
            conn.edit_config(['hostname test', 'netconf ssh'])
    """

    __rpc__ = ['get_config', 'edit_config', 'get_capabilities', 'get']

    supports_commit = False
    supports_replace = False
    supports_diff = False

    network_os = None
    network_os_version = None
    network_os_model = None
    network_os_hostname = None


    def __init__(self, connection):
        self.connection = connection
        self.history = list()
        import q; q('start')

    def _alarm_handler(self, signum, frame):
        """Alarm handler raised in case of command timeout """
        display.display('closing shell due to command timeout (%s seconds).' % self.connection._play_context.timeout, log_only=True)
        self.close()

    def send_command(self, command, prompt=None, answer=None, sendonly=False,
            newline=True, prompt_retry_check=False, nolog=True):
        """Executes a command over the device connection

        This method will execute a command over the device connection and
        return the results to the caller.  This method will also perform
        logging of any commands based on the `nolog` argument.

        :param command: The command to send over the connection to the device
        :param prompt: A regex pattern to evalue the expected prompt from the command
        :param answer: The answer to respond with if the prompt is matched.
        :param sendonly: Bool value that will send the command but not wait for a result.
        :param newline: Bool value that will append the newline character to the command
        :param prompt_retry_check: Bool value for trying to detect more prompts
        :nolog: Bool value to control the logging of commands and outputs

        :returns: The output from the device after executing the command
        """
        if nolog not in (True, False):
            nolog = True

        nolog = False

        for arg in (sendonly, newline, prompt_retry_check):
            if arg not in (None, True, False):
                raise ValueError('invalid value for %s' % arg)

        kwargs = {
            'command': to_bytes(command),
            'sendonly': sendonly,
            'newline': newline,
            'prompt_retry_check': prompt_retry_check
        }

        if prompt is not None:
            kwargs['prompt'] = to_bytes(prompt)

        if answer is not None:
            kwargs['answer'] = to_bytes(answer)

        resp = self.connection.send(**kwargs)

        if nolog:
            self.history.append(('******', '*****'))
        else:
            self.history.append((kwargs['command'], resp))

        return resp

    def get_base_rpc(self):
        """Returns list of base rpc method supported by remote device"""
        return self.__rpc__

    def get_history(self):
        """ Returns the history file for all commands

        This will return a log of all the commands that have been sent to
        the device and all of the output recevied.  By default, all commands
        and output will be redacted unless explicitly configured otherwise.

        :returns: An ordered list of command, output pairs
        """
        return self.history

    @abstractmethod
    def get_config(self, source='running', filter=None):
        """Retrieves the specified configuration from the device

        This method will retrieve the configuration specified by source and
        return it to the caller as a string.  Subsequent calls to this method
        will retrieve a new configuration from the device

        :param source: The configuration source to return from the device.
            This argument accepts either `running` or `startup` as valid values.

        :param filter: For devices that support configuration filtering, this
            keyword argument is used to filter the returned configuration.
            The use of this keyword argument is device dependent adn will be
            silently ignored on devices that do not support it.

        :returns: The device configuration as specified by the source argument.
        """
        pass

    @abstractmethod
    def edit_config(self, candidate, commit=None, replace=None):
        """Loads the candidate configuration into the network device

        This method will load the specified candidate config into the device
        and merge with the current configuration unless replace is set to
        True.  If the device does not support config replace an errors
        is returned.

        :param candidate: The configuration to load into the device and merge
            with the current running configuration

        :param commit: Boolean value that indicates if the device candidate
            configuration should be merged (committed) with the active
            configuration or discarded.

        :param replace: Specifies the provided config value should replace
            the configuration running on the remote device.  If the device
            doesn't support config replace, an error is return.

        :returns: None if the configuration is successfully loaded otherwise
            returns an error
        """
        pass

    def get(self, command=None, prompt=None, answer=None, sendonly=False, newline=True):
        """Execute specified command on remote device
        This method will retrieve the specified data and
        return it to the caller as a string.
        :args:
             command: command in string format to be executed on remote device
             prompt: the expected prompt generated by executing command.
                            This can be a string or a list of strings (optional)
             answer: the string to respond to the prompt with (optional)
             sendonly: bool to disable waiting for response, default is false (optional)
        :returns: Returns output received from remote device as byte string
        """
        return self.send_command(command, prompt, answer, sendonly, newline)

    def get_capabilities(self):
        """ Returns the basic capabilities of the network device

        This method will provide some basic facts about the device and
        what capabilities it has to modify the configuration.  The minimum
        return from this method takes the following format.

            {
                "network_api": "cliconf",
                "rpc": [list of supported rpcs],
                "device_info": {
                    "network_os": <str>,
                    "network_os_version": <str>,
                    "network_os_model": <str>,
                    "network_os_hostname": <str>
                },
                "operations": {
                    "commit": <bool>,
                    "replace: <bool>,
                    "diff": <bool>
                }
            }

        :returns: dict value with list of capabilities.
        """
        return json.dumps({
            'network_api': 'cliconf',
            'rpc': self.__rpc__,
            'device_info': {
                'network_os': self.network_os,
                'network_os_version': self.network_os_version,
                'network_os_model': self.network_os_model,
                'network_os_hostname': self.network_os_hostname
            },
            'operations': {
                'commit': self.supports_commit,
                'replace': self.supports_replace,
                'diff', self.supports_diff
            }
        })


    def commit(self, comment=None):
        """Commit configuration changes

        This method will perform the commit operation on a previously loaded
        candidate configuration that was loaded using `edit_config()`.  If
        there is a candidate configuration, it will be committed to the
        active configuration.  If there is not a candidate configuration, this
        method should just silently return.

        :returns: None
        """
        return self.connection.method_not_found("commit is not supported by network_os %s" % self._play_context.network_os)

    def discard_changes(self):
        """Discard candidate configuration

        This method will discard the current candidate configuration if one
        is present.  If there is no candidate configuration currently loaded,
        then this method should just silently return

        :returns: None
        """
        return self.connection.method_not_found("discard_changes is not supported by network_os %s" % self._play_context.network_os)

    def copy_file(self, source=None, destination=None, proto='scp'):
        """Copies file over scp/sftp to remote device"""
        ssh = self.connection.paramiko_conn._connect_uncached()
        if proto == 'scp':
            if not HAS_SCP:
                self.connection.internal_error("Required library scp is not installed.  Please install it using `pip install scp`")
            with SCPClient(ssh.get_transport()) as scp:
                scp.put(source, destination)
        elif proto == 'sftp':
            with ssh.open_sftp() as sftp:
                sftp.put(source, destination)

    def get_file(self, source=None, destination=None, proto='scp'):
        """Fetch file over scp/sftp from remote device"""
        ssh = self.connection.paramiko_conn._connect_uncached()
        if proto == 'scp':
            if not HAS_SCP:
                self.connection.internal_error("Required library scp is not installed.  Please install it using `pip install scp`")
            with SCPClient(ssh.get_transport()) as scp:
                scp.get(source, destination)
        elif proto == 'sftp':
            with ssh.open_sftp() as sftp:
                sftp.get(source, destination)
