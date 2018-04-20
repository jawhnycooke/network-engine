#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2018, Ansible by Red Hat, inc
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'network'}

DOCUMENTATION = """
"""

EXAMPLES = """
"""

RETURN = """
"""
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection
from ansible.module_utils._text import to_text

def main():
    """main entry point for module execution
    """
    argument_spec = dict(
        content=dict(required=True),
        commit=dict(default=False, type='bool'),
        replace=dict(default=False, type='bool')
    )

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=True)

    config = to_text(module.params['config']).split('\n')

    commit = module.params['commit']
    replace = module.params['replace']

    result = {'changed': False}

    connection = Connection(module._socket_path)
    capabilities = module.from_json(connection.get_capabilities())

    can_commit = capabilities.get('commit')
    can_replace = capabilities.get('replace')
    can_diff = capabilities.get('diff')

    if replace is True and can_replace is not True:
        module.fail_json(msg='config replace is not supported on this device')

    # if the device doesn't support commit there is no reason to try
    # the config because we are in check_mode.  Just set the changed
    # value to True.
    if module.check_mode and not can_commit:
        module.warn('checking proposed config is not supported on this device, '
                    'statically setting changed flag to True')
        result['changed'] = True

    else:
        try:
            # set the commit keyword argument as the inverse of check_mode to
            # commit the candidate configuration on the device.  If commit is
            # False, the `edit_config` call will discard any changes
            commit = not module.check_mode

            # load the candidate configuration into the device and perform
            # either the commit or discard operation
            diff = connection.edit_config(config=config, commit=commit, replace=replace)

            # check if diff is suppored on the device otherwise do not trust
            # the return value of None as nothing changed.
            if can_diff:
                result['changed'] = True if diff else False
                if module._dict:
                    result['diff'] = {'prepared': diff}
            else:
                # since the device does not provide a diff function, assume
                # the config was changed and set changed to True
                module.warn('config diff is not supported on this device, '
                            'statically setting changed flag to True')
                result['changed'] = True

        except Exception as exc:
            module.fail_json(msg=to_text(exc))

    history = connection.get_history()
    commands= [h[0] for h in history]
    result['history'] = commands

    module.exit_json(**result)


if __name__ == '__main__':
    main()
