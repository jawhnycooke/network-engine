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

import re

from itertools import chain

from ansible.plugins.cliconf import CliconfBase
from ansible.module_utils._text import to_bytes, to_text
from ansible.module_utils.network.common.utils import to_list


class Cliconf(CliconfBase):

    _device_operations = {
        'supports_commit': True,
        'supports_replace': False,
        'supports_diff': True
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
                return self._device_facts
        except AttributeError:
            device_facts = {}

            device_facts['network_os'] = 'vyos'

            reply = self.get(b'show version')
            data = to_text(reply, errors='surrogate_or_strict').strip()

            match = re.search(r'Version:\s*(\S+)', data)
            if match:
                device_facts['network_os_version'] = match.group(1)

            match = re.search(r'HW model:\s*(\S+)', data)
            if match:
                device_facts['network_os_model'] = match.group(1)

            reply = self.get(b'show host name')
            device_facts['network_os_hostname'] = to_text(reply, errors='surrogate_or_strict').strip()

            setattr(self, '_device_facts', device_facts)
            return self.get_facts(key)

    def get_config(self, source='running', filter=None):
        """ Retrieves the device active configuration

        This method will return the current active configuration from
        the device.  The returned configuration from VyOS will be the
        `commands` version of the configuration.

        The keyword arguments for this method are not supported on VyOS
        platforms and are silently ignored.

        :param source: not supported
        :param filter: not supported

        :returns: current configuration as a string
        """
        cmd = 'show configuration'
        if filter:
            cmd += ' %s' % filter
        if filter
        return self.send_command(to_bytes(cmd))

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

        try:
            for cmd in chain(['configure'], candidate):
                self.send_command(to_bytes(cmd))
        except:
            self.send_command(b'exit discard')
            raise

        diff = self.send_command(b'compare')
        if diff:
            diff = to_text(diff).strip()

        if commit:
            # TODO add support for commit comment
            # command: commit comment <str>
            self.send_command(b'commit')
        else:
            self.send_command(b'exit discard')

        return diff
