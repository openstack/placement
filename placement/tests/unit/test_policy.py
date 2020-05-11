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
from unittest import mock

import fixtures
from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslo_policy import policy as oslo_policy

from placement import conf
from placement import context
from placement import exception
from placement import policy
from placement.tests.unit import base
from placement.tests.unit import policy_fixture


class PlacementPolicyTestCase(base.ContextTestCase):
    """Tests interactions with placement policy."""
    def setUp(self):
        super(PlacementPolicyTestCase, self).setUp()
        config = cfg.ConfigOpts()
        self.conf_fixture = self.useFixture(config_fixture.Config(config))
        conf.register_opts(config)
        self.ctxt = context.RequestContext(user_id='fake', project_id='fake')
        self.target = {'user_id': 'fake', 'project_id': 'fake'}
        # A value is required in the database connection opt for conf to
        # parse.
        self.conf_fixture.config(connection='stub', group='placement_database')
        config([], default_config_files=[])
        self.ctxt.config = config
        policy.reset()
        self.addCleanup(policy.reset)

    def test_modified_policy_reloads(self):
        """Creates a temporary policy.yaml file and tests
        authorizations against a fake rule between updates to the physical
        policy file.
        """
        tempdir = self.useFixture(fixtures.TempDir())
        tmpfilename = os.path.join(tempdir.path, 'policy.yaml')

        self.conf_fixture.config(
            group='oslo_policy', policy_file=tmpfilename)

        # We have to create the file before initializing the policy enforcer
        # otherwise it falls back to using CONF.placement.policy_file. This
        # can be removed when the deprecated CONF.placement.policy_file option
        # is removed.
        with open(tmpfilename, "w") as policyfile:
            policyfile.write('# The policy file is empty.')

        action = 'placement:test'

        # Load the default action and rule (defaults to "any").
        enforcer = policy._get_enforcer(self.conf_fixture.conf)
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
        fixture = self.useFixture(
            policy_fixture.PolicyFixture(self.conf_fixture))
        fixture.set_rules({'placement': '!'})
        self.assertFalse(
            policy.authorize(
                self.ctxt, 'placement', self.target, do_raise=False))

    @mock.patch('placement.policy.LOG.warning')
    def test_default_fallback_placement_policy_file_no_exist(self, mock_warn):
        """Tests that by default the policy enforcer will fallback to the
        [placement]/policy_file when [oslo_policy]/policy_file does not
        exist. In this case the placement policy file does not exist so no
        warning about using it should be logged.
        """
        # Make sure oslo_policy and placement use different policy_file
        # defaults (the former uses policy.json, the latter uses policy.yaml).
        config = self.conf_fixture.conf
        self.assertNotEqual(config.oslo_policy.policy_file,
                            config.placement.policy_file)
        enforcer = policy._get_enforcer(config)
        self.assertEqual(config.placement.policy_file, enforcer.policy_file)
        # There should not be a warning logged since the policy file does not
        # actually exist.
        mock_warn.assert_not_called()

    @mock.patch('placement.policy.LOG.warning')
    def test_default_fallback_placement_policy_file(self, mock_warn):
        """Tests that by default the policy enforcer will fallback to the
        [placement]/policy_file when [oslo_policy]/policy_file does not
        exist. In this case the plcaement policy file exists, like in the case
        of using it to define custom rules, so a warning is logged.
        """
        tempdir = self.useFixture(fixtures.TempDir())
        tmpfilename = os.path.join(tempdir.path, 'policy.yaml')
        self.conf_fixture.config(group='placement', policy_file=tmpfilename)
        # We have to create the file before initializing the policy enforcer
        # otherwise it falls back to using CONF.placement.policy_file. This
        # can be removed when the deprecated CONF.placement.policy_file option
        # is removed.
        with open(tmpfilename, "w") as policyfile:
            policyfile.write('# I would normally have custom rules in here.')
        config = self.conf_fixture.conf
        enforcer = policy._get_enforcer(config)
        self.assertEqual(config.placement.policy_file, enforcer.policy_file)
        # There should not be a warning logged since the policy file does not
        # actually exist.
        mock_warn.assert_called_once_with(
            '[placement]/policy_file is deprecated. Use '
            '[oslo_policy]/policy_file instead.')

    @mock.patch('placement.policy.LOG.error')
    def test_init_from_oslo_policy_file_exists_same_policy_file_name(
            self, mock_log_error):
        """Tests a scenario where the [oslo_policy]/policy_file exists and
        is the same name as the [placement]/policy_file so no error is logged
        since we'll use the file from oslo_policy config.
        """
        # Configure [oslo_policy]/policy_file and [placement]/policy_file with
        # the same name.
        tempdir = self.useFixture(fixtures.TempDir())
        tmpfilename = os.path.join(tempdir.path, 'policy.yaml')
        self.conf_fixture.config(group='oslo_policy', policy_file=tmpfilename)
        self.conf_fixture.config(group='placement', policy_file=tmpfilename)
        # Create the [oslo_policy]/policy_file.
        with open(tmpfilename, "w") as policyfile:
            policyfile.write('# Assume upgrade with existing custom policy.')
        config = self.conf_fixture.conf
        policy._get_enforcer(config)
        # Checking what the Enforcer is using for a policy file does not really
        # matter too much since they are pointing at the same file, just make
        # sure we did not log an error.
        mock_log_error.assert_not_called()

    @mock.patch('placement.policy.LOG.error')
    def test_init_from_oslo_file_exists_different_name_no_placement_file(
            self, mock_log_error):
        """Tests a scenario where the [oslo_policy]/policy_file exists and
        has a different name from the [placement]/policy_file but the
        [placement]/policy_file does not exist so no error is logged.
        """
        # Configure [oslo_policy]/policy_file and [placement]/policy_file with
        # different names.
        tempdir = self.useFixture(fixtures.TempDir())
        tmpfilename = os.path.join(tempdir.path, 'policy.yaml')
        self.conf_fixture.config(group='oslo_policy', policy_file=tmpfilename)
        self.conf_fixture.config(group='placement', policy_file='policy.json')
        # Create the [oslo_policy]/policy_file.
        with open(tmpfilename, "w") as policyfile:
            policyfile.write('# Assume upgrade with existing custom policy.')
        config = self.conf_fixture.conf
        enforcer = policy._get_enforcer(config)
        self.assertEqual(config.oslo_policy.policy_file, enforcer.policy_file)
        # Though the policy file names are different, the placement version
        # does not exist while the oslo policy one does so no error is logged.
        mock_log_error.assert_not_called()

    @mock.patch('placement.policy.LOG.error')
    def test_init_from_oslo_file_exists_different_name_placement_file_exists(
            self, mock_log_error):
        """Tests a scenario where the [oslo_policy]/policy_file exists and
        has a different name from the [placement]/policy_file and the
        [placement]/policy_file exists so an error is logged.
        """
        # Configure [oslo_policy]/policy_file and [placement]/policy_file with
        # different names.
        tempdir = self.useFixture(fixtures.TempDir())
        oslo_name = os.path.join(tempdir.path, 'policy.yaml')
        self.conf_fixture.config(group='oslo_policy', policy_file=oslo_name)
        placement_name = os.path.join(tempdir.path, 'placement-policy.yaml')
        self.conf_fixture.config(group='placement', policy_file=placement_name)
        # Create the [oslo_policy]/policy_file.
        with open(oslo_name, "w") as oslo_policy_file:
            oslo_policy_file.write('# New oslo policy config.')
        # Create the [placement]/policy_file.
        with open(placement_name, "w") as placement_policy_file:
            placement_policy_file.write('# Old placement policy file.')
        config = self.conf_fixture.conf
        enforcer = policy._get_enforcer(config)
        self.assertEqual(config.oslo_policy.policy_file, enforcer.policy_file)
        # An error should be logged since we're going to use the oslo policy
        # file but there is a placement policy file with a different name that
        # also exists.
        mock_log_error.assert_called_once()
        self.assertIn('you need to clean up your configuration file',
                      mock_log_error.call_args[0][0])
