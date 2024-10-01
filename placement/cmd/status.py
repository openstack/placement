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

import sqlalchemy as sa
import sys

from oslo_config import cfg
from oslo_upgradecheck import common_checks
from oslo_upgradecheck import upgradecheck

from placement import conf
from placement import context
from placement.db.sqlalchemy import models
from placement import db_api


class Checks(upgradecheck.UpgradeCommands):
    """Checks for the ``placement-status upgrade check`` command.

    Various upgrade checks should be added as separate methods in this class
    and added to _upgrade_checks tuple.
    """

    def __init__(self, config):
        self.config = config
        self.ctxt = context.RequestContext(config=config)

    @db_api.placement_context_manager.reader
    def _check_missing_root_ids(self, ctxt):
        exists = sa.exists().where(
            models.ResourceProvider.root_provider_id == sa.null())
        ret = ctxt.session.query(exists).scalar()
        return ret

    def _check_root_provider_ids(self):
        """Starting in Queens with the 1.28 microversion, resource_providers
        table has the root_provider_id column. Older resource_providers with
        no root provider id records will be online migrated when the
        "placement-manage db online_data_migrations" command is run during
        an upgrade. This status check emits a failure if there are missing
        root provider ids to remind operators to perform the data migration.
        """
        if self._check_missing_root_ids(self.ctxt):
            return upgradecheck.Result(
                upgradecheck.Code.FAILURE,
                details='There is at least one resource provider table '
                        'record which misses its root provider id. '
                        'Run the "placement-manage db '
                        'online_data_migrations" command.')
        return upgradecheck.Result(upgradecheck.Code.SUCCESS)

    @db_api.placement_context_manager.reader
    def _count_missing_consumers(self, ctxt):
        allocation = models.Allocation.__table__
        consumer = models.Consumer.__table__
        return ctxt.session.execute(
            sa.select(
                sa.func.count(sa.distinct(allocation.c.consumer_id))
            ).select_from(
                allocation.outerjoin(
                    consumer,
                    allocation.c.consumer_id == consumer.c.uuid,
                )
            ).where(
                consumer.c.id.is_(None)
            )
        ).fetchone()[0]

    def _check_incomplete_consumers(self):
        """Allocations created with microversion<1.8 prior to Rocky will not
        have an associated consumers table record. Starting in Rocky with
        the 1.28 microversion, consumer generations were added to avoid
        multiple processes overwriting allocations. Older allocations with
        incomplete consumer records will be online migrated when accessed
        via the REST API or when the
        "placement-manage db online_data_migrations" command is run during
        an upgrade. This status check emits a warning if there are incomplete
        consumers to remind operators to perform the data migration.

        Note that normally we would not add an upgrade status check to simply
        mirror an online data migration since online data migrations should
        be part of deploying/upgrading placement automation. However, with
        placement being freshly extracted from nova, this check serves as a
        friendly reminder and because the data migration will eventually be
        removed from nova along with the rest of the placement code.
        """
        missing_consumer_count = self._count_missing_consumers(self.ctxt)
        if missing_consumer_count:
            # We found missing consumers for existing allocations so return
            # a warning and tell the user to run the online data migrations.
            return upgradecheck.Result(
                upgradecheck.Code.WARNING,
                details='There are %s incomplete consumers table records '
                        'for existing allocations. Run the '
                        '"placement-manage db online_data_migrations" '
                        'command.' % missing_consumer_count)
        # No missing consumers (or no allocations [fresh install?]) so it's OK.
        return upgradecheck.Result(upgradecheck.Code.SUCCESS)

    def _check_policy_json(self):
        """A wrapper passing a proper config object when calling the generic
        policy json check.
        """
        return common_checks.check_policy_json(self, self.config)

    # The format of the check functions is to return an
    # oslo_upgradecheck.upgradecheck.Result
    # object with the appropriate
    # oslo_upgradecheck.upgradecheck.Code and details set.
    # If the check hits warnings or failures then those should be stored
    # in the returned Result's "details" attribute. The
    # summary will be rolled up at the end of the check() method.
    _upgrade_checks = (
        ('Missing Root Provider IDs', _check_root_provider_ids),
        ('Incomplete Consumers', _check_incomplete_consumers),
        ("Policy File JSON to YAML Migration", _check_policy_json),
    )


def main():
    # Set up the configuration to configure the database.
    config = cfg.ConfigOpts()
    conf.register_opts(config)
    # Register cli opts before parsing args.
    upgradecheck.register_cli_options(config, Checks(config))
    # A slice of sys.argv is provided to pass the command line
    # arguments for processing, without the name of the calling
    # script ('placement-status'). If we were using
    # upgradecheck.main() directly, it would do it for us, but
    # we do not because of the need to configure the database
    # first.
    config(args=sys.argv[1:], project='placement')
    db_api.configure(config)
    return upgradecheck.run(config)


if __name__ == '__main__':
    sys.exit(main())
