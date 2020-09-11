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

from alembic import context
from oslo_config import cfg
from oslo_db import exception as db_exc

from placement import conf
from placement.db.sqlalchemy import models
from placement import db_api as placement_db


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = models.BASE.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    try:
        connectable = placement_db.get_placement_engine()
    except db_exc.CantStartEngineError:
        # We are being called from a context where the database hasn't been
        # configured so we need to set up Config and config the database.
        # This is usually the alembic command line.
        config = cfg.ConfigOpts()
        conf.register_opts(config)
        config([], project="placement", default_config_files=None)
        placement_db.configure(config)
        connectable = placement_db.get_placement_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise Exception('offline mode disabled')
else:
    run_migrations_online()
