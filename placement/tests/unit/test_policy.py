#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslo_policy import policy as oslo_policy
import testtools

from placement import context
from placement import exception
from placement import policy
from placement.tests.unit import policy_fixture
from placement import util


CONF = cfg.CONF


class PlacementPolicyTestCase(testtools.TestCase):
    """Tests interactions with placement policy."""
    def setUp(self):
        super(PlacementPolicyTestCase, self).setUp()
        self.conf = self.useFixture(config_fixture.Config(CONF)).conf
        self.ctxt = context.RequestContext(user_id='fake', project_id='fake')
        self.target = {'user_id': 'fake', 'project_id': 'fake'}
        CONF([], default_config_files=[])

    def test_modified_policy_reloads(self):
        """Creates a temporary placement-policy.yaml file and tests
        authorizations against a fake rule between updates to the physical
        policy file.
        """
        with util.tempdir() as tmpdir:
            tmpfilename = os.path.join(tmpdir, 'placement-policy.yaml')

            self.conf.set_default(
                'policy_file', tmpfilename, group='placement')

            action = 'placement:test'
            # Expect PolicyNotRegistered since defaults are not yet loaded.
            self.assertRaises(oslo_policy.PolicyNotRegistered,
                              policy.authorize, self.ctxt, action, self.target)

            # Load the default action and rule (defaults to "any").
            enforcer = policy.get_enforcer()
            rule = oslo_policy.RuleDefault(action, '')
            enforcer.register_default(rule)

            # Now auth should work because the action is registered and anyone
            # can perform the action.
            policy.authorize(self.ctxt, action, self.target)

            # Now update the policy file and reload it to disable the action
            # from all users.
            with open(tmpfilename, "w") as policyfile:
                policyfile.write('"%s": "!"' % action)
            enforcer.load_rules(force_reload=True)
            self.assertRaises(exception.PolicyNotAuthorized, policy.authorize,
                              self.ctxt, action, self.target)

    def test_authorize_do_raise_false(self):
        """Tests that authorize does not raise an exception when the check
        fails.
        """
        fixture = self.useFixture(policy_fixture.PolicyFixture())
        fixture.set_rules({'placement': '!'})
        self.assertFalse(
            policy.authorize(
                self.ctxt, 'placement', self.target, do_raise=False))
