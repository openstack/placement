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

import mock
from oslo_config import cfg
from oslo_config import fixture as config_fixture
import testtools

from placement import conf
from placement import context
from placement import resource_class_cache as rc_cache


RESOURCE_CLASS_NAME = 'DISK_GB'
RESOURCE_CLASS_ID = 2


def fake_ensure_cache(ctxt):
    cache = rc_cache.RC_CACHE = mock.MagicMock()
    cache.string_from_id.return_value = RESOURCE_CLASS_NAME
    cache.id_from_string.return_value = RESOURCE_CLASS_ID


class TestCase(testtools.TestCase):
    """Base class for other tests in this file.

    It establishes the RequestContext used as self.context in the tests.
    """

    def setUp(self):
        super(TestCase, self).setUp()
        self.user_id = 'fake-user'
        self.project_id = 'fake-project'
        self.context = context.RequestContext(self.user_id, self.project_id)
        config = cfg.ConfigOpts()
        self.conf_fixture = self.useFixture(config_fixture.Config(config))
        conf.register_opts(config)
        self.context.config = config
