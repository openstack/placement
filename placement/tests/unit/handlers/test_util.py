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
"""Unit tests for the utility functions used by the placement DB."""

import fixtures
import microversion_parse
from oslo_config import cfg
from oslo_config import fixture as config_fixture
from oslo_utils.fixture import uuidsentinel
import webob

from placement import conf
from placement import context
from placement import exception
from placement.handlers import util
from placement import microversion
from placement.objects import consumer as consumer_obj
from placement.objects import project as project_obj
from placement.objects import user as user_obj
from placement.tests.unit import base


class TestEnsureConsumer(base.ContextTestCase):
    def setUp(self):
        super(TestEnsureConsumer, self).setUp()
        self.conf = cfg.ConfigOpts()
        self.useFixture(config_fixture.Config(self.conf))
        conf.register_opts(self.conf)
        self.mock_project_get = self.useFixture(fixtures.MockPatch(
            'placement.objects.project.'
            'Project.get_by_external_id')).mock
        self.mock_user_get = self.useFixture(fixtures.MockPatch(
            'placement.objects.user.'
            'User.get_by_external_id')).mock
        self.mock_consumer_get = self.useFixture(fixtures.MockPatch(
            'placement.objects.consumer.'
            'Consumer.get_by_uuid')).mock
        self.mock_project_create = self.useFixture(fixtures.MockPatch(
            'placement.objects.project.'
            'Project.create')).mock
        self.mock_user_create = self.useFixture(fixtures.MockPatch(
            'placement.objects.user.'
            'User.create')).mock
        self.mock_consumer_create = self.useFixture(fixtures.MockPatch(
            'placement.objects.consumer.'
            'Consumer.create')).mock
        self.mock_consumer_update = self.useFixture(fixtures.MockPatch(
            'placement.objects.consumer.'
            'Consumer.update')).mock
        self.ctx = context.RequestContext(user_id='fake', project_id='fake')
        self.ctx.config = self.conf
        self.consumer_id = uuidsentinel.consumer
        self.project_id = uuidsentinel.project
        self.user_id = uuidsentinel.user
        mv_parsed = microversion_parse.Version(1, 27)
        mv_parsed.max_version = microversion_parse.parse_version_string(
            microversion.max_version_string())
        mv_parsed.min_version = microversion_parse.parse_version_string(
            microversion.min_version_string())
        self.before_version = mv_parsed
        mv_parsed = microversion_parse.Version(1, 28)
        mv_parsed.max_version = microversion_parse.parse_version_string(
            microversion.max_version_string())
        mv_parsed.min_version = microversion_parse.parse_version_string(
            microversion.min_version_string())
        self.after_version = mv_parsed
        mv_parsed = microversion_parse.Version(1, 38)
        mv_parsed.max_version = microversion_parse.parse_version_string(
            microversion.max_version_string())
        mv_parsed.min_version = microversion_parse.parse_version_string(
            microversion.min_version_string())
        self.cons_type_req_version = mv_parsed

    def test_no_existing_project_user_consumer_before_gen_success(self):
        """Tests that we don't require a consumer_generation=None before the
        appropriate microversion.
        """
        self.mock_project_get.side_effect = exception.NotFound
        self.mock_user_get.side_effect = exception.NotFound
        self.mock_consumer_get.side_effect = exception.NotFound

        consumer_gen = 1  # should be ignored
        util.ensure_consumer(
            self.ctx, self.consumer_id, self.project_id, self.user_id,
            consumer_gen, 'TYPE', self.before_version)

        self.mock_project_get.assert_called_once_with(
            self.ctx, self.project_id)
        self.mock_user_get.assert_called_once_with(
            self.ctx, self.user_id)
        self.mock_consumer_get.assert_called_once_with(
            self.ctx, self.consumer_id)
        self.mock_project_create.assert_called_once()
        self.mock_user_create.assert_called_once()
        self.mock_consumer_create.assert_called_once()

    def test_no_existing_project_user_consumer_after_gen_success(self):
        """Tests that we require a consumer_generation=None after the
        appropriate microversion.
        """
        self.mock_project_get.side_effect = exception.NotFound
        self.mock_user_get.side_effect = exception.NotFound
        self.mock_consumer_get.side_effect = exception.NotFound

        consumer_gen = None  # should NOT be ignored (and None is expected)
        util.ensure_consumer(
            self.ctx, self.consumer_id, self.project_id, self.user_id,
            consumer_gen, 'TYPE', self.after_version)

        self.mock_project_get.assert_called_once_with(
            self.ctx, self.project_id)
        self.mock_user_get.assert_called_once_with(
            self.ctx, self.user_id)
        self.mock_consumer_get.assert_called_once_with(
            self.ctx, self.consumer_id)
        self.mock_project_create.assert_called_once()
        self.mock_user_create.assert_called_once()
        self.mock_consumer_create.assert_called_once()

    def test_no_existing_project_user_consumer_after_gen_fail(self):
        """Tests that we require a consumer_generation=None after the
        appropriate microversion and that None is the expected value.
        """
        self.mock_project_get.side_effect = exception.NotFound
        self.mock_user_get.side_effect = exception.NotFound
        self.mock_consumer_get.side_effect = exception.NotFound

        consumer_gen = 1  # should NOT be ignored (and 1 is not expected)
        self.assertRaises(
            webob.exc.HTTPConflict,
            util.ensure_consumer,
            self.ctx, self.consumer_id, self.project_id, self.user_id,
            consumer_gen, 'TYPE', self.after_version)

    def test_no_existing_project_user_consumer_use_incomplete(self):
        """Verify that if the project_id arg is None, that we fall back to the
        CONF options for incomplete project and user ID.
        """
        self.mock_project_get.side_effect = exception.NotFound
        self.mock_user_get.side_effect = exception.NotFound
        self.mock_consumer_get.side_effect = exception.NotFound

        consumer_gen = None  # should NOT be ignored (and None is expected)
        util.ensure_consumer(
            self.ctx, self.consumer_id, None, None,
            consumer_gen, 'TYPE', self.before_version)

        self.mock_project_get.assert_called_once_with(
            self.ctx, self.conf.placement.incomplete_consumer_project_id)
        self.mock_user_get.assert_called_once_with(
            self.ctx, self.conf.placement.incomplete_consumer_user_id)
        self.mock_consumer_get.assert_called_once_with(
            self.ctx, self.consumer_id)
        self.mock_project_create.assert_called_once()
        self.mock_user_create.assert_called_once()
        self.mock_consumer_create.assert_called_once()

    def test_existing_project_no_existing_consumer_before_gen_success(self):
        """Check that if we find an existing project and user, that we use
        those found objects in creating the consumer. Do not require a consumer
        generation before the appropriate microversion.
        """
        proj = project_obj.Project(self.ctx, id=1, external_id=self.project_id)
        self.mock_project_get.return_value = proj
        user = user_obj.User(self.ctx, id=1, external_id=self.user_id)
        self.mock_user_get.return_value = user
        self.mock_consumer_get.side_effect = exception.NotFound

        consumer_gen = None  # should be ignored
        util.ensure_consumer(
            self.ctx, self.consumer_id, self.project_id, self.user_id,
            consumer_gen, 'TYPE', self.before_version)

        self.mock_project_create.assert_not_called()
        self.mock_user_create.assert_not_called()
        self.mock_consumer_create.assert_called_once()

    def test_existing_consumer_after_gen_matches_supplied_gen(self):
        """Tests that we require a consumer_generation after the
        appropriate microversion and that when the consumer already exists,
        then we ensure a matching generation is supplied
        """
        proj = project_obj.Project(self.ctx, id=1, external_id=self.project_id)
        self.mock_project_get.return_value = proj
        user = user_obj.User(self.ctx, id=1, external_id=self.user_id)
        self.mock_user_get.return_value = user
        consumer = consumer_obj.Consumer(
            self.ctx, id=1, project=proj, user=user, generation=2)
        self.mock_consumer_get.return_value = consumer

        consumer_gen = 2  # should NOT be ignored (and 2 is expected)
        util.ensure_consumer(
            self.ctx, self.consumer_id, self.project_id, self.user_id,
            consumer_gen, 'TYPE', self.after_version)

        self.mock_project_create.assert_not_called()
        self.mock_user_create.assert_not_called()
        self.mock_consumer_create.assert_not_called()

    def test_existing_consumer_after_gen_fail(self):
        """Tests that we require a consumer_generation after the
        appropriate microversion and that when the consumer already exists,
        then we raise a 400 when there is a mismatch on the existing
        generation.
        """
        proj = project_obj.Project(self.ctx, id=1, external_id=self.project_id)
        self.mock_project_get.return_value = proj
        user = user_obj.User(self.ctx, id=1, external_id=self.user_id)
        self.mock_user_get.return_value = user
        consumer = consumer_obj.Consumer(
            self.ctx, id=1, project=proj, user=user, generation=42)
        self.mock_consumer_get.return_value = consumer

        consumer_gen = 2  # should NOT be ignored (and 2 is NOT expected)
        self.assertRaises(
            webob.exc.HTTPConflict,
            util.ensure_consumer,
            self.ctx, self.consumer_id, self.project_id, self.user_id,
            consumer_gen, 'TYPE', self.after_version)

    def test_existing_consumer_different_consumer_type_supplied(self):
        """Tests that we update a consumer's type ID if the one supplied by the
        user is different than the one in the existing record.
        """
        proj = project_obj.Project(self.ctx, id=1, external_id=self.project_id)
        self.mock_project_get.return_value = proj
        user = user_obj.User(self.ctx, id=1, external_id=self.user_id)
        self.mock_user_get.return_value = user
        # Consumer currently has type ID = 1
        consumer = consumer_obj.Consumer(
            self.ctx, id=1, project=proj, user=user, generation=1,
            consumer_type_id=1)
        self.mock_consumer_get.return_value = consumer

        consumer_gen = 1
        consumer, created_new_consumer, request_attr = util.ensure_consumer(
            self.ctx, self.consumer_id, self.project_id, self.user_id,
            consumer_gen, 'TYPE', self.cons_type_req_version)
        util.update_consumers([consumer], {consumer.uuid: request_attr})
        # Expect 1 call to update() to update to the supplied consumer type ID
        self.mock_consumer_update.assert_called_once_with()
        # Consumer should have the new consumer type from the cache
        self.assertEqual(
            self.ctx.ct_cache.id_from_string.return_value,
            consumer.consumer_type_id)

    def test_consumer_create_exists_different_consumer_type_supplied(self):
        """Tests that we update a consumer's type ID if the one supplied by a
        racing request is different than the one in the existing (recently
        created) record.
        """
        proj = project_obj.Project(self.ctx, id=1, external_id=self.project_id)
        self.mock_project_get.return_value = proj
        user = user_obj.User(self.ctx, id=1, external_id=self.user_id)
        self.mock_user_get.return_value = user
        # Request A recently created consumer has type ID = 1
        consumer = consumer_obj.Consumer(
            self.ctx, id=1, project=proj, user=user, generation=1,
            consumer_type_id=1, uuid=uuidsentinel.consumer)
        self.mock_consumer_get.return_value = consumer
        # Request B will encounter ConsumerExists as Request A just created it
        self.mock_consumer_create.side_effect = (
            exception.ConsumerExists(uuid=uuidsentinel.consumer))

        consumer_gen = 1
        consumer, created_new_consumer, request_attr = util.ensure_consumer(
            self.ctx, self.consumer_id, self.project_id, self.user_id,
            consumer_gen, 'TYPE', self.cons_type_req_version)
        util.update_consumers([consumer], {consumer.uuid: request_attr})
        # Expect 1 call to update() to update to the supplied consumer type ID
        self.mock_consumer_update.assert_called_once_with()
        # Consumer should have the new consumer type from the cache
        self.assertEqual(
            self.ctx.ct_cache.id_from_string.return_value,
            consumer.consumer_type_id)
