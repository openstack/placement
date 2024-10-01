# Copyright 2012 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy

import fixtures
from oslo_policy import policy as oslo_policy

from placement.conf import paths
from placement import policies
from placement import policy as placement_policy


class PolicyFixture(fixtures.Fixture):

    def __init__(self, conf_fixture):
        self.conf_fixture = conf_fixture
        super(PolicyFixture, self).__init__()

    """Load the default placement policy for tests."""

    def setUp(self):
        super(PolicyFixture, self).setUp()
        policy_file = paths.state_path_def('etc/placement/policy.yaml')
        self.conf_fixture.config(group='oslo_policy', policy_file=policy_file)
        placement_policy.reset()
        # because oslo.policy has a nasty habit of modifying the default rules
        # we provide, we must pass a copy of the rules rather then the rules
        # themselves
        placement_policy.init(
            self.conf_fixture.conf,
            suppress_deprecation_warnings=True,
            rules=copy.deepcopy(policies.list_rules()))
        self.addCleanup(placement_policy.reset)

    @staticmethod
    def set_rules(rules, overwrite=True):
        """Set placement policy rules.

        .. note:: The rules must first be registered via the
                  Enforcer.register_defaults method.

        :param rules: dict of action=rule mappings to set
        :param overwrite: Whether to overwrite current rules or update them
                          with the new rules.
        """
        enforcer = placement_policy.get_enforcer()
        enforcer.set_rules(oslo_policy.Rules.from_dict(rules),
                           overwrite=overwrite)
