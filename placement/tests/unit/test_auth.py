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
"""Unit tests for the auth middleware used by the Placement service.

Most of the functionality of the auth middleware is tested in functional
and integration tests but sometimes it is more convenient or accurate to
use unit tests.
"""

from keystonemiddleware import auth_token
from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslo_policy import opts as policy_opts
import testtools
import webob

from placement import conf
from placement import deploy


class RootNoAuth(testtools.TestCase):
    """Confirm that no auth is required for accessing root."""

    def setUp(self):
        """Establish config defaults for middlewares."""
        super(RootNoAuth, self).setUp()
        config = cfg.ConfigOpts()
        conf_fixture = self.useFixture(config_fixture.Config(config))
        conf.register_opts(conf_fixture.conf)
        auth_token_opts = auth_token.AUTH_TOKEN_OPTS[0][1]
        conf_fixture.register_opts(auth_token_opts, group='keystone_authtoken')
        www_authenticate_uri = 'http://example.com/identity'
        conf_fixture.config(
            www_authenticate_uri=www_authenticate_uri,
            group='keystone_authtoken')
        # ensure that the auth_token middleware is chosen
        conf_fixture.config(auth_strategy='keystone', group='api')
        # register and default policy opts (referenced by deploy)
        policy_opts.set_defaults(conf_fixture.conf)
        self.conf = conf_fixture.conf
        self.app = deploy.deploy(self.conf)

    def _test_root_req(self, req):
        # set no environ on req, thus no auth
        req.environ['REMOTE_ADDR'] = '127.0.0.1'

        response = req.get_response(self.app)
        data = response.json_body
        self.assertEqual('CURRENT', data['versions'][0]['status'])

    def test_slash_no_auth(self):
        """Accessing / requires no auth."""
        req = webob.Request.blank('/', method='GET')
        self._test_root_req(req)

    def test_no_slash_no_auth(self):
        """Accessing '' requires no auth."""
        req = webob.Request.blank('', method='GET')
        self._test_root_req(req)

    def test_auth_elsewhere(self):
        """Make sure auth is happening."""
        req = webob.Request.blank('/resource_providers', method='GET')
        req.environ['REMOTE_ADDR'] = '127.0.0.1'
        response = req.get_response(self.app)
        self.assertEqual('401 Unauthorized', response.status)
