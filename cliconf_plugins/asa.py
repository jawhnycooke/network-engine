#
# Copyright (c) 2017 Red Hat Inc.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import re
import collections

from itertools import chain

from ansible.module_utils._text import to_bytes, to_text
from ansible.module_utils.network.common.utils import to_list
from ansible.plugins.cliconf import CliconfBase, enable_mode


class Cliconf(CliconfBase):

    _device_operations = {
        'supports_commit': False,
        'supports_replace': False,
        'supports_diff': False
    }

    def get_operations(self, key=None):
        if key:
            return self._device_operations.get(key)
        else:
            return self._device_operations

    def get_facts(self, key=None):
        try:
            if key:
                return self._device_facts.get(key)
            else:
                return self._device.facts
        except AttributeError:
            facts = {}

            facts['network_os'] = 'asa'
            reply = self.get(b'show version')
            data = to_text(reply, errors='surrogate_or_strict').strip()

            match = re.search(r'Version (\S+),', data)
            if match:
                facts['network_os_version'] = match.group(1)

            match = re.search(r'^Model Id:\s+(.+) \(revision', data, re.M)
            if match:
                facts['network_os_model'] = match.group(1)

            match = re.search(r'^(.+) up', data, re.M)
            if match:
                facts['network_os_hostname'] = match.group(1)

            setattr(self, '_device_facts', facts)

            return self.get_facts(key)

    @enable_mode
    def get_config(self, source='running', filter=None):
        lookup = {'running': 'running-config', 'startup': 'startup-config'}
        if source not in lookup:
            raise ValueError("fetching configuration from %s is not supported" % source)

        cmd = b'show %s ' % lookup[source]

        flags = [] if filter is None else to_list(filter)
        cmd += ' '.join(flags)
        cmd = cmd.strip()

        return self.send_command(cmd)

    @enable_mode
    def edit_config(self, candidate, commit=None, replace=None):
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

        if commit is True or replace is True:
            raise ValueError('commit and/or replace are not supported on this platform')

        for line in candidate:
            if line != 'end' and line[0] != '!':
                if not isinstance(line, collections.Mapping):
                    line = {'command': line}
                resp = self.send_command(**line)

        self.send_command(b'end')

