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

import logging
import os
import warnings

import fixtures
from sqlalchemy import exc as sqla_exc


class NullHandler(logging.Handler):
    """custom default NullHandler to attempt to format the record.

    Used in conjunction with Logging below to detect formatting errors
    in debug logs.
    """

    def handle(self, record):
        self.format(record)

    def emit(self, record):
        pass

    def createLock(self):
        self.lock = None


class Logging(fixtures.Fixture):
    """A logging fixture providing two important fixtures.

    One is to capture logs for later inspection.

    The other is to make sure that DEBUG logs, even if not captured,
    are formatted.
    """

    def __init__(self):
        super().__init__()
        self.level = logging.INFO
        debug = os.environ.get('OS_DEBUG')
        if debug in ('True', 'true', '1', 'yes'):
            self.level = logging.DEBUG
        elif debug and debug not in ('False', 'false', '0', 'no'):
            levels = {
                name: getattr(logging, name)
                for name in (
                    'DEBUG', 'INFO', 'WARN', 'WARNING', 'ERROR', 'CRITICAL'
                )
            }
            levels['TRACE'] = 5
            try:
                self.level = int(debug)
            except ValueError:
                if debug not in levels:
                    raise ValueError('OS_DEBUG=%s is invalid.' % debug)
                self.level = levels[debug]
        self.capture_logs = os.environ.get('OS_LOG_CAPTURE') in (
            'True', 'true', '1', 'yes'
        )
        self.logger = None

    def setUp(self):
        super().setUp()
        log_format = '%(levelname)8s [%(name)s] %(message)s'
        if self.capture_logs:
            fake_logger = fixtures.FakeLogger(
                format=log_format, level=self.level, nuke_handlers=True
            )
            self.logger = self.useFixture(fake_logger)
        else:
            logging.basicConfig(format=log_format, level=self.level)
        if self.level > logging.DEBUG:
            handler = NullHandler()
            self.useFixture(fixtures.LogHandler(handler, nuke_handlers=False))
            handler.setLevel(logging.DEBUG)


class WarningsFixture(fixtures.Fixture):
    """Filter or escalates certain warnings during test runs.

    Add additional entries as required. Remove when obsolete.
    """

    def setUp(self):
        super(WarningsFixture, self).setUp()

        self._original_warning_filters = warnings.filters[:]

        warnings.simplefilter("once", DeprecationWarning)

        # Ignore policy scope warnings.
        warnings.filterwarnings(
            'ignore',
            message="Policy .* failed scope check",
            category=UserWarning)

        # The UUIDFields emits a warning if the value is not a  valid UUID.
        # Let's escalate that to an exception in the test to prevent adding
        # violations.
        warnings.filterwarnings('error', message=".*invalid UUID.*")

        # Prevent us introducing unmapped columns
        warnings.filterwarnings(
            'error',
            category=sqla_exc.SAWarning)

        # Configure SQLAlchemy warnings
        warnings.filterwarnings(
            'ignore',
            category=sqla_exc.SADeprecationWarning)

        warnings.filterwarnings(
            'error',
            module='placement',
            category=sqla_exc.SADeprecationWarning)

        self.addCleanup(self._reset_warning_filters)

    def _reset_warning_filters(self):
        warnings.filters[:] = self._original_warning_filters
