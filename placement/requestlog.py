# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Simple middleware for request logging that also sets request id.

We combine these two pieces of functionality in one middleware because we want
to be sure that we have a DEBUG log at the very start of the request, with a
a global request id, and an INFO log at the very end of the request.
"""

from oslo_context import context
from oslo_log import log as logging
from oslo_middleware import request_id
import webob.dec

from placement import microversion

LOG = logging.getLogger(__name__)


class RequestLog(request_id.RequestId):
    """WSGI Middleware to write a simple request log with a global request id.

    Borrowed from Paste Translogger and incorporating
    oslo_middleware.request_id.RequestId.

    This also guards against a missing "Accept" header.
    """

    def __init__(self, application):
        self.application = application

    @webob.dec.wsgify
    def __call__(self, req):
        # This duplicates code from __call__ on RequestId, but because of the
        # way that method is structured, calling super is not workable.
        self.set_global_req_id(req)

        # We must instantiate a Request context, otherwise the LOG in the
        # next line will not produce the expected output where we would expect
        # to see request ids. Instead we get '[-]'. Presumably there be magic
        # here...
        ctx = context.RequestContext.from_environ(req.environ)
        req.environ[request_id.ENV_REQUEST_ID] = ctx.request_id

        LOG.debug('Starting request: %s "%s %s"',
                  req.remote_addr, req.method,
                  self._get_uri(req.environ))

        # Set the accept header if it is not otherwise set or is '*/*'. This
        # ensures that error responses will be in JSON.
        accept = req.environ.get('HTTP_ACCEPT')
        if not accept or accept == '*/*':
            req.environ['HTTP_ACCEPT'] = 'application/json'

        if LOG.isEnabledFor(logging.INFO):
            response = req.get_response(self._log_app)
        else:
            response = req.get_response(self.application)

        return_headers = [request_id.HTTP_RESP_HEADER_REQUEST_ID]
        return_headers.extend(self.compat_headers)

        for header in return_headers:
            if header not in response.headers:
                response.headers.add(header, ctx.request_id)
        return response

    @staticmethod
    def _get_uri(environ):
        req_uri = (environ.get('SCRIPT_NAME', '') +
                   environ.get('PATH_INFO', ''))
        if environ.get('QUERY_STRING'):
            req_uri += '?' + environ['QUERY_STRING']
        return req_uri

    def _log_app(self, environ, start_response):
        req_uri = self._get_uri(environ)

        def replacement_start_response(status, headers, exc_info=None):
            """We need to gaze at the content-length, if set, to
            write log info.
            """
            size = None
            for name, value in headers:
                if name.lower() == 'content-length':
                    size = value
            self.write_log(environ, req_uri, status, size)
            return start_response(status, headers, exc_info)

        return self.application(environ, replacement_start_response)

    def write_log(self, environ, req_uri, status, size):
        """Write the log info out in a formatted form to ``LOG.info``.
        """
        if size is None:
            size = '-'
        LOG.info('%(REMOTE_ADDR)s "%(REQUEST_METHOD)s %(REQUEST_URI)s" '
                 'status: %(status)s len: %(bytes)s '
                 'microversion: %(microversion)s',
                 {'REMOTE_ADDR': environ.get('REMOTE_ADDR', '-'),
                  'REQUEST_METHOD': environ['REQUEST_METHOD'],
                  'REQUEST_URI': req_uri,
                  'status': status.split(None, 1)[0],
                  'bytes': size,
                  'microversion': environ.get(
                  microversion.MICROVERSION_ENVIRON, '-')})
