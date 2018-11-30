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
from __future__ import absolute_import

import fixtures
from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslo_policy import opts as policy_opts
from oslo_utils import uuidutils
from wsgi_intercept import interceptor

from placement import conf
from placement import deploy
from placement.tests import fixtures as db_fixture
from placement.tests.unit import policy_fixture


class PlacementFixture(fixtures.Fixture):
    """A fixture to placement operations.

    Runs a local WSGI server bound on a free port and having the Placement
    application with NoAuth middleware.

    It's possible to ask for a specific token when running the fixtures so
    all calls would be passing this token.

    This fixture takes care of starting a fixture for an in-RAM placement
    database, unless the db kwarg is False.

    Used by other services, including nova, for functional tests.
    """
    def __init__(self, token='admin', conf_fixture=None, db=True):
        self.token = token
        self.db = db
        self.conf_fixture = conf_fixture

    def setUp(self):
        super(PlacementFixture, self).setUp()
        if not self.conf_fixture:
            config = cfg.ConfigOpts()
            self.conf_fixture = self.useFixture(config_fixture.Config(config))
        conf.register_opts(self.conf_fixture.conf)

        if self.db:
            self.useFixture(db_fixture.Database(self.conf_fixture,
                                                set_config=True))
        policy_opts.set_defaults(self.conf_fixture.conf)
        self.conf_fixture.config(group='api', auth_strategy='noauth2')

        self.conf_fixture.conf([], default_config_files=[])

        self.useFixture(policy_fixture.PolicyFixture(self.conf_fixture))

        loader = deploy.loadapp(self.conf_fixture.conf)
        app = lambda: loader
        self.endpoint = 'http://%s/placement' % uuidutils.generate_uuid()
        intercept = interceptor.RequestsInterceptor(app, url=self.endpoint)
        intercept.install_intercept()
        self.addCleanup(intercept.uninstall_intercept)
