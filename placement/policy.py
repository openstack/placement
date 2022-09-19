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
"""Policy Enforcement for placement API."""

import typing as ty

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import opts as policy_opts
from oslo_policy import policy
from oslo_utils import excutils

from placement import exception
from placement import policies


LOG = logging.getLogger(__name__)
_ENFORCER = None


def reset():
    """Used to reset the global _ENFORCER between test runs."""
    global _ENFORCER
    if _ENFORCER:
        _ENFORCER.clear()
        _ENFORCER = None


def init(
    conf: cfg.ConfigOpts,
    suppress_deprecation_warnings: bool = False,
    rules: ty.List[policy.RuleDefault] = None,
):
    """Init an Enforcer class. Sets the _ENFORCER global.

    :param conf: A ConfigOpts object to load configuration from.
    :param suppress_deprecation_warnings: **Test only** Suppress policy
        deprecation warnings to avoid polluting logs.
    :param rules: **Test only** The default rules to initialise.
    """
    global _ENFORCER
    if not _ENFORCER:
        _enforcer = policy.Enforcer(conf)

        # NOTE(gmann): Explicitly disable the warnings for policies changing
        # their default check_str. During the policy-defaults-refresh work, all
        # the policy defaults have been changed and warnings for each policy
        # started filling the logs limit for various tool.
        # Once we move to new defaults only world then we can enable these
        # warnings again.
        _enforcer.suppress_default_change_warnings = True
        _enforcer.suppress_deprecation_warnings = suppress_deprecation_warnings

        _enforcer.register_defaults(rules or policies.list_rules())
        _enforcer.load_rules()
        _ENFORCER = _enforcer


def get_enforcer():
    # This method is used by oslopolicy CLI scripts in order to generate policy
    # files from overrides on disk and defaults in code. We can just pass an
    # empty list and let oslo do the config lifting for us.
    cfg.CONF([], project='placement')
    # TODO(gmann): Remove setting the default value of config policy_file
    # once oslo_policy change the default value to 'policy.yaml'.
    # https://github.com/openstack/oslo.policy/blob/a626ad12fe5a3abd49d70e3e5b95589d279ab578/oslo_policy/opts.py#L49
    policy_opts.set_defaults(cfg.CONF, 'policy.yaml')
    return _get_enforcer(cfg.CONF)


def _get_enforcer(conf):
    init(conf)
    return _ENFORCER


def authorize(context, action, target, do_raise=True):
    """Verifies that the action is valid on the target in this context.

    :param context: instance of placement.context.RequestContext
    :param action: string representing the action to be checked
        this should be colon separated for clarity, i.e.
        ``placement:resource_providers:list``
    :param target: dictionary representing the object of the action;
        for object creation this should be a dictionary representing the
        owner of the object e.g. ``{'project_id': context.project_id}``.
    :param do_raise: if True (the default), raises PolicyNotAuthorized;
        if False, returns False
    :raises placement.exception.PolicyNotAuthorized: if verification fails and
        do_raise is True.
    :returns: non-False value (not necessarily "True") if authorized, and the
        exact value False if not authorized and do_raise is False.
    """
    try:
        # NOTE(mriedem): The "action" kwarg is for the PolicyNotAuthorized exc.
        return _ENFORCER.authorize(
            action, target, context, do_raise=do_raise,
            exc=exception.PolicyNotAuthorized, action=action)
    except policy.PolicyNotRegistered:
        with excutils.save_and_reraise_exception():
            LOG.exception('Policy not registered')
    except policy.InvalidScope:
        raise exception.PolicyNotAuthorized(action)
    except Exception:
        with excutils.save_and_reraise_exception():
            credentials = context.to_policy_values()
            LOG.debug('Policy check for %(action)s failed with credentials '
                      '%(credentials)s',
                      {'action': action, 'credentials': credentials})
