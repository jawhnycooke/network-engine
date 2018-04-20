#
# (c) 2017 Red Hat Inc.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import json
import time
import collections

from itertools import chain

from ansible.plugins.cliconf import CliconfBase, enable_mode
from ansible.module_utils.network.common.utils import to_list
from ansible.module_utils._text import to_text


class Cliconf(CliconfBase):

    @property
    def supports_sessions(self):
        return self.device_operations('supports_sessions')

    def get_operations(self, key=None):
        """ Collect and return device operations

        This method will return the various supported operations on the
        device to the caller.  This provides the calling function with an
        indication of what is supported by the platform.

        :param key: Operation key name to return

        :returns: Dict of all operations or individual operation if key provided
        """
        try:
            if key:
                return self._device_operations.get(key)
            else:
                return self._device_operations
        except AttributeError:
            use_sessions = os.getenv('ANSIBLE_EOS_USE_SESSIONS', True)
            try:
                use_sessions = int(use_sessions)
            except:
                use_sessions = True
            if use_sessions is True:
                resp = self.get(b'show configuration session')
                use_sesssions = 'error' not in resp

            device_operations = {}
            for k in ('commit', 'replace', 'diff', 'sessions'):
                device_operations['supports_%s' % k] = bool(use_sessions)

            setattr(self, '_device_operations', device_operations)
            return self.get_operations(key)

    def get_facts(self, key=None):
        """ Collect and return device facts

        This method will retrieve facts about the device and return those
        facts to the caller.  If the keyword `key` is provided, only the
        fact that matches the `key` will be returned.  If the `key` does
        not exist, an error is raised.

        :param key: Fact name to return

        :returns: Dict of all facts or individual fact if key provided
        """
        try:
            if key:
                return self._device_facts.get(key)
            else:
                return self._device_facts
        except AttributeError:
            facts = {'network_os': 'eos'}

            resp = self.get(b'show version | json')
            data = json.loads(resp)
            facts.update({
                'network_os_version': data['version'],
                'network_os_model': data['modelName']
            })

            resp = self.get(b'show hostname | json')
            data = json.loads(resp)
            facts.update({'network_os_hostname': data['hostname']})

            setattr(self, '_device_facts', facts)
            return self.get_facts(key)


    @enable_mode
    def get_config(self, source='running', filter=None):
        """ Implements the get_config method for cliconf

        This method will return the current configuration from the device
        as specified by the source kwarg.  This method supports source values
        of either `running` or `startup`.

        The format kwarg is used to return the desired configuration format.
        By default, this method will return the device configuration in its
        native text format.  Other possible values for format are `json`.

        The filter kwarg is used to append any additional filter to the command
        for retrieving the configuation. The filter keyword argument values are
        OS version dependent.
        """
        lookup = {'running': 'running-config', 'startup': 'startup-config'}
        if source not in lookup:
            return self.invalid_params("fetching configuration from %s is not supported" % source)

        cmd = b'show %s ' % lookup[source]

        flags = [] if filter is None else to_list(filter)
        cmd += ' '.join(flags)
        cmd = cmd.strip()

        # TODO: add additional introspection of the output here before
        # returning it.  Look for things like "This is an uncoverted command"
        return self.send_command(cmd)

    def _loader(self, candidate):
        """ Internal method that will load the configuration

        This method wil load the configuration line by line.  It expects the
        session to already be in the right mode (config mode) and will not
        exit config mode.  Those operations are left to other layers.

        :param candidate: The candidate configuration to load

        :returns: None
        """
        for line in candidate:
            if line != 'end' and line[0] != '!':
                if not isinstance(line, collections.Mapping):
                    line = {'command': line}
                resp = self.send_command(**line)

    @enable_mode
    def edit_config(self, candidate, commit=None, replace=None):
        """ Edit the configuration on the remote device

        When loading the specified config, this method will first check if
        the device supports config sessions.

        If the device does not support config sessions, the configuration
        will be immediately loaded to the device and merged with the
        current running config.

        If the device does support config sessions, then the configuration
        session will be started and the configuration loaded.  This method
        will not activate the loaded configuration.

        :param candidate: The device configuration to load

        :param commit: Bool flag to indicate if the candidate configuration
            should be merged with the active configuration or discarded

        :param replace: Bool flag to indicate if the configuration should be
            replaced.

        :returns: a diff of the configuration changes as a string
        """
        commit = commit or False
        if commit not in (True, False):
            raise ValueError('`commit` must be a bool, got %s' % commit)

        replace = replace or False
        if replace not in (True, False):
            raise ValueError('`replace` must be a bool, got %s' % replace)

        if candidate is None:
            raise ValueError('must provide a candidate config to load')
        else:
            candidate = to_text(candidate).strip().split('\n')

        diff = None

        # since the device doesn't support sessions, short circuit the session
        # commands and just load the configuration
        if not self.supports_sessions:
            # TODO need to handle the replace use case here
            if replace is True:
                raise ValueError('config replace not supported for merge operations')

            if commit is False:
                raise ValueError('cannot load candidate configuration when commit is False')

            self._loader(list(chain([b'configure'], candidate)))

        else:
            session = 'ansible_%s' % int(time.time())
            self.send_command(b'configure session %s' % session)

            if replace:
                self.send_command(b'rollback clean-config')

            try:
                self._loader(config)
            except:
                self.send_command(b'abort')
                raise

            diff = self.send_command(b'show session-config diffs')
            if diff:
                diff = to_text(diff).strip()

            if commit is True:
                self.send_command(b'commit')
            else:
                self.send_command(b'abort')

        self.send_command(b'end')

        return diff
