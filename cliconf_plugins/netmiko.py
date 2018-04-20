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
import collections

from itertools import chain

from ansible.module_utils._text import to_bytes, to_text
from ansible.module_utils.network.common.utils import to_list
from ansible.plugins.cliconf import CliconfBase, enable_mode
from ansible.errors import AnsibleError


class Cliconf(CliconfBase):

    __rpc__ = ['get_capabilities', 'get']

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
            device_facts = {
                'network_os': self.connection.device_type
            }
            setattr(self, '_device_facts', device_facts)
            return self.device_facts(key)

    def get_config(self, source='running', filter=None):
        raise AnsibleError('edit_config is not supported when using netmiko')

    def edit_config(self, candidate, commit=None, replace=None):
        raise AnsibleError('edit_config is not supported when using netmiko')


