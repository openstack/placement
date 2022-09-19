# All Rights Reserved.
#
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
"""Unit tests for the deploy function used to build the Placement service."""

from keystonemiddleware import auth_token
from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslo_policy import opts as policy_opts
import testtools
import webob

from placement import conf
from placement import deploy


class DeployTest(testtools.TestCase):

    def test_auth_middleware_factory(self):
        """Make sure that configuration settings make their way to
        the keystone middleware correctly.
        """
        config = cfg.ConfigOpts()
        conf_fixture = self.useFixture(config_fixture.Config(config))
        conf.register_opts(conf_fixture.conf)
        # NOTE(cdent): There appears to be no simple way to get the list of
        # options used by the auth_token middleware. So we pull from an
        # existing data structure.
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
        app = deploy.deploy(conf_fixture.conf)
        req = webob.Request.blank('/resource_providers', method="GET")

        response = req.get_response(app)

        auth_header = response.headers['www-authenticate']
        self.assertIn(www_authenticate_uri, auth_header)
        self.assertIn('keystone uri=', auth_header.lower())
