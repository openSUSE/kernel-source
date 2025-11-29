from www_authenticate import www_authenticate
import urllib.request
import urllib.parse
import email.policy
import http.client
import binascii
import certifi
import base64
import email
import json
import yaml
import ssl
import sys

class APIError(RuntimeError):
    pass

setattr(http.client.HTTPResponse, 'ok', property(lambda r: r.status < 300 and r.status >= 200))

def _read_content(r):  # this could be a lambda in python 3.8 with walrus operator
    if not hasattr(r, '_read_data'):
        r._read_data = r.read()
    return r._read_data
setattr(http.client.HTTPResponse, 'content', property(_read_content))
setattr(http.client.HTTPResponse, 'text', property(lambda r: r.content.decode()))  # FIXME encoding
http.client.HTTPResponse.json = lambda r: json.loads(r.text)  # FIXME content type

def parse_content_type(content_type):
    header = email.policy.EmailPolicy.header_factory('content-type', content_type)
    return (header.content_type, dict(header.params))

def _get_encoding(r):  # another case for walrus
    ct = r.headers.get('content-type', None)
    if ct:
        ct =  parse_content_type(ct)[1].get('charset', None)
    return ct
setattr(http.client.HTTPResponse, 'encoding', property(_get_encoding))

setattr(http.client.HTTPResponse, 'status_message_pretty', property(lambda r: '%s %s %i %s' % (r.url, r.method, r.status, r.reason)))
def _raise_for_status(r):
    if not r.ok:
        raise APIError(r.status_message_pretty)
http.client.HTTPResponse.raise_for_status = _raise_for_status

def _dic_update(self, dic):
    for k in dic.keys():
        self[k] = dic[k]
email.message.EmailMessage.update = _dic_update

class NonRaisingHTTPErrorProcessor(urllib.request.HTTPErrorProcessor):
    # completely undocumented API
    def http_response(self, request, response):
        # This would handle redirect inside urllib but authentication and logging would need to be handled as well
        # As the API is not documented and has no logging implemented by upstream this would be challenging
        if False and (code in [301, 302, 303, 307, 308] and m in ['GET', 'HEAD']
                 or code in [301, 302, 303] and m == 'POST'):
            code, msg, hdrs = response.code, response.msg, response.info()
            response = self.parent.error('http', request, response, code, msg, hdrs)
        return response
    https_response = http_response

class SavingHTTPCookieProcessor(urllib.request.HTTPCookieProcessor):
    # another completely undocumented API
    def http_response(self, request, response):  # Only override cookie extraction, adding is handled by base
        if 'Set-Cookie' in response.headers:  # Unlike base don't bother if the header is not present
            self.cookiejar.extract_cookies(response, request)
            try:
                self.cookiejar.save()  # Presumably some cookie was extracted, save it to disk
            except Exception as e:
                sys.stderr.write("Error saving cookies: %s\n" % (repr(e),))
        return response
    https_response = http_response

class API:
    def __init__(self, URL, logfile, ca=None):
        self.url = URL
        if not ca:
            ca = certifi.where()
        self.ca = ca
        self._to_close = None
        if logfile:
            try:
                _ = logfile.write
            except AttributeError:
                logfile = open(logfile, 'a')
                self._to_close = logfile
        self.logfile = logfile
        if hasattr(ssl, 'PROTOCOL_TLS_SERVER'):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        else:  # SLE 12
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
        context.load_verify_locations(self.ca)
        if hasattr(self, 'cookiejar'):  # LWPCookieJar is false :/
            cp = SavingHTTPCookieProcessor(self.cookiejar)
        else:
            cp = urllib.request.HTTPCookieProcessor()
        self._opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                                   NonRaisingHTTPErrorProcessor(), cp)

    def __del__(self):
        if self._to_close:
            self._to_close.close()

    def redact_auth(self, string):
        redacted = 'RedacteD'
        parts = string.split(' ', 1)
        # preserve the authentication type if present
        if len(parts) > 1:
            parts[1] = redacted
        else:
            parts[0] = redacted
        return ' '.join(parts)

    def redact_auth_hdrs(self, headers):
        headers = dict(headers)
        for i in headers.keys():
            if i.lower() == 'authorization':
                headers[i] = self.redact_auth(headers[i])
            if i.lower() == 'cookie':
                # This would fail if the cookie value included a semicolon
                # Not even sure how to use the standard cookie parser for this
                headers[i] = ';'.join([c.split('=', 1)[0] + '=RedacteD' for c in headers[i].split(';')])
        return headers

    def redact_auth_args(self, args):
        if args.get('headers', None):
            args = dict(args)
            args['headers'] = self.redact_auth_hdrs(args['headers'])
        return args

    def redact_content(self, data):
        if isinstance(data, list):
            return [self.redact_content(x) for x in data]
        if isinstance(data, dict):
            result = {}
            for i in data.keys():
                if (i == 'content' or i == 'body' or  i == 'text' ) and data[i] and len(data[i]) > 4096:
                    result[i] = 'RedacteD'
                else:
                    if (i == 'content') and data[i] and (isinstance(data[i], str) or isinstance(data[i], bytes)):
                        try:
                            result['content_decoded'] = base64.standard_b64decode(data[i]).decode(errors='surrogateescape')
                        except binascii.Error:
                            None
                    result[i] = self.redact_content(data[i])
            return result
        return data

    def redact_one_cookie(self, c):
        # This would fail if the cookie value included a semicolon
        # On the other hand, using the standard parser reorders the cookie flags
        parts = c.strip().split(';',1)
        return parts[0].split('=',1)[0] + '=RedacteD;' + parts[1]

    def redact_cookies_hdr(self, headers):
        result = []
        for i in headers.items():
            v = i[1]
            if i[0].lower() == 'set-cookie':
                v = self.redact_one_cookie(i[1])
            result.append({i[0]:v})
        return result

    def format_request(self, method, path, args, r):
        data = {
            'method': method,
            'path': path,
            'args': self.redact_auth_args(args),
            'code': r.status,
            'reason': r.reason,
            'encoding': r.encoding,
            'headers': self.redact_cookies_hdr(r.headers),
            'url': r.url,
            'request': {
                'url': r.request.full_url,
                'method': r.request.method,
                'headers': self.redact_auth_hdrs(r.request.headers),
                'unredirected_hdrs': self.redact_auth_hdrs(r.request.unredirected_hdrs),
                'body': r.request.data,
                }}
        try:
            data['json'] = r.json()
        except Exception:  # throws unknown exception, differs from documentation
            try:
                data['text'] = r.text
            except UnicodeDecodeError:
                None
            data['content'] = r.content
        return '---\n' + yaml.dump(self.redact_content(data))

    def log(self, method, path, args, r):
        self.logfile.write(self.format_request(method, path, args, r))

    def header_json(self):
        return {'Content-type': 'application/json'}

    def call(self, method, path, **kwargs):
        for arg in kwargs.keys():
            if arg not in ['data', 'json', 'params', 'headers', 'redirected', 'reauthenticated']:
                raise ValueError('Unexpected argumen %s' % (arg,))
        if len(path) > 0 and path[0] != '/':
            raise ValueError('Path has to start with /')
        if kwargs.get('data', None) and kwargs.get('json', None):
            raise ValueError('Only one of data and json can be specified')
        headers = dict(kwargs.get('headers', {}))
        if kwargs.get('json', None):
            data = json.dumps(kwargs['json'])
            headers['Content-Type'] = 'application/json'
        else:
            data = kwargs.get('data', None)
        if kwargs.get('params', None):
            params = urllib.parse.urlencode(kwargs['params'])
            if method == 'GET' or method == 'HEAD':
                params = '?' + params
                pr = urllib.parse.urlparse(self.url + path)
                if len(pr.query) > 0:
                    raise ValueError('params provided but path already includes query')
                if len(pr.fragment) > 0:
                    raise ValueError('params provided but path already includes fragment')
            else:
                if data:
                    raise ValueError('With method ' + method + 'params are to be sent as data but data already given')
                data = params
                params = ''
        else:
            params = ''
        if isinstance(data, str):
            data = data.encode()
        if not kwargs.get('reauthenticated', None) and not hasattr(self, 'cookiejar'):  # LWPCookieJar is false :/
            kwargs['reauthenticated'] = True  # Only try to authenticate once per request
            headers.update(self.auth_header({}))
        req = urllib.request.Request(method=method, url=self.url + path + params, data=data, headers=headers)
        r = self._opener.open(req)
        r.request = req
        r.method = method
        if self.logfile:
            self.log(method, path, kwargs, r)
        if not kwargs.get('reauthenticated', None) and r.status == 401:
            kwargs['reauthenticated'] = True  # Only try to authenticate once per request
            wwwa = {}
            if 'www-authenticate' in r.headers:
                wwwa = www_authenticate.parse(r.headers['www-authenticate'])
            headers = dict(kwargs.get('headers', {}))
            headers.update(self.auth_header(wwwa))
            kwargs['headers'] = headers
            return self.call(method, path, **kwargs)
        if not kwargs.get('redirected', None) and r.status in [301, 302, 303, 307, 308] and method in ['GET', 'HEAD']:
            if r.headers.get('location', None) or r.headers.get('uri', None):
                kwargs['redirected'] = True  # Only one level of redirection supported, does not require loop tracking
                if r.headers.get('location', None):
                    url = r.headers['location']
                else:
                    url = r.headers['uri']
                path = urllib.parse.urlparse(url).path  # no cross-host redirect support
            return self.call(method, path, **kwargs)
        return r

    def get(self, path, **kwargs):
        return self.call('GET', path, **kwargs)

    def put(self, path, **kwargs):
        return self.call('PUT', path, **kwargs)

    def head(self, path, **kwargs):
        return self.call('HEAD', path, **kwargs)

    def post(self, path, **kwargs):
        return self.call('POST', path, **kwargs)

    def patch(self, path, **kwargs):
        return self.call('PATCH', path, **kwargs)

    def delete(self, path, **kwargs):
        return self.call('DELETE', path, **kwargs)

    def check(self, method, path, **kwargs):
        r = self.call(method, path, **kwargs)
        r.raise_for_status()
        return r

    def check_get(self, path, **kwargs):
        return self.check('GET', path, **kwargs)

    def check_put(self, path, **kwargs):
        return self.check('PUT', path, **kwargs)

    def check_head(self, path, **kwargs):
        return self.check('HEAD', path, **kwargs)

    def check_post(self, path, **kwargs):
        return self.check('POST', path, **kwargs)

    def check_patch(self, path, **kwargs):
        return self.check('PATCH', path, **kwargs)

    def check_delete(self, path, **kwargs):
        return self.check('DELETE', path, **kwargs)

    def check_exists(self, path, **kwargs):
        r = self.get(path, **kwargs)  # Some gitea endpoints don't like HEAD request
        if r.status == 404:
            return False
        r.raise_for_status()
        return r
