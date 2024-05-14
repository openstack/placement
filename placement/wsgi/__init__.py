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
"""WSGI script for Placement API

WSGI handler for running Placement API under Apache2, nginx, gunicorn etc.
"""

import logging as py_logging
import os
import os.path

from oslo_config import cfg
from oslo_log import log as logging
from oslo_middleware import cors
from oslo_utils import importutils
import pbr.version

from placement import conf
from placement import db_api
from placement import deploy


osprofiler = importutils.try_import('osprofiler')
osprofiler_initializer = importutils.try_import('osprofiler.initializer')
profiler = importutils.try_import('osprofiler.opts')


CONFIG_FILE = 'placement.conf'


# The distribution name is required here, not package.
version_info = pbr.version.VersionInfo('openstack-placement')


def setup_logging(config):
    # Any dependent libraries that have unhelp debug levels should be
    # pinned to a higher default.
    extra_log_level_defaults = [
        'routes=INFO',
    ]
    logging.set_defaults(default_log_levels=logging.get_default_log_levels() +
                         extra_log_level_defaults)
    logging.setup(config, 'placement')
    py_logging.captureWarnings(True)


def _get_config_files(env=None):
    """Return a list of one file or None describing config location.

    If None, that means oslo.config will look in the default locations
    for a config file.
    """
    if env is None:
        env = os.environ

    dirname = env.get('OS_PLACEMENT_CONFIG_DIR', '').strip()
    if dirname:
        return [os.path.join(dirname, CONFIG_FILE)]
    else:
        return None


def _parse_args(config, argv, default_config_files):
    # register placement's config options
    conf.register_opts(config)

    if profiler:
        profiler.set_defaults(config)

    _set_middleware_defaults()

    config(argv[1:], project='placement',
           version=version_info.version_string(),
           default_config_files=default_config_files)


def setup_profiler(config):
    if osprofiler and config.profiler.enabled:
        osprofiler.initializer.init_from_conf(
            conf=config,
            context={},
            project="placement",
            service="placement",
            host="??")


def _set_middleware_defaults():
    """Update default configuration options for oslo.middleware."""
    cors.set_defaults(
        allow_headers=['X-Auth-Token',
                       'X-Openstack-Request-Id',
                       'X-Identity-Status',
                       'X-Roles',
                       'X-Service-Catalog',
                       'X-User-Id',
                       'X-Tenant-Id',
                       'OpenStack-API-Version'],
        expose_headers=['X-Auth-Token',
                        'X-Openstack-Request-Id',
                        'X-Subject-Token',
                        'X-Service-Token',
                        'OpenStack-API-Version'],
        allow_methods=['GET',
                       'PUT',
                       'POST',
                       'DELETE',
                       'PATCH']
    )


def init_application():
    # initialize the config system
    conffiles = _get_config_files()

    config = cfg.ConfigOpts()
    conf.register_opts(config)

    # This will raise cfg.RequiredOptError when a required option is not set
    # (notably the database connection string). We want this to be a hard fail
    # that prevents the application from starting. The error will show up in
    # the wsgi server's logs.
    _parse_args(config, [], default_config_files=conffiles)
    # initialize the logging system
    setup_logging(config)

    # configure database
    db_api.configure(config)

    # dump conf at debug if log_options
    if config.log_options:
        config.log_opt_values(
            logging.getLogger(__name__),
            logging.DEBUG)

    setup_profiler(config)

    # build and return our WSGI app
    return deploy.loadapp(config)
