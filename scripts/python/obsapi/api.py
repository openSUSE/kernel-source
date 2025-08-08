import requests
import binascii
import base64
import yaml

class APIError(RuntimeError):
    pass

class API:
    def __init__(self, URL, logfile):
        self.url = URL
        self._to_close = None
        if logfile:
            try:
                _ = logfile.write
            except AttributeError:
                logfile = open(logfile, 'a')
                self._to_close = logfile
        self.logfile = logfile

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
        auth = 'authorization'
        headers = dict(headers)
        for i in headers.keys():
            if i.lower() == auth:
                headers[i] = self.redact_auth(headers[i])
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

    def format_request(self, method, path, args, r):
        data = {
            'method': method,
            'path': path,
            'args': self.redact_auth_args(args),
            'code': r.status_code,
            'reason': r.reason,
            'history': r.history,
            'encoding': r.encoding,
            'apparent_encoding': r.apparent_encoding,
            'cookies': requests.utils.dict_from_cookiejar(r.cookies),
            'elapsed': str(r.elapsed),
            'headers': dict(r.headers),
            'is_redirect': r.is_redirect,
            'url': r.url,
            'request': {
                'url': r.request.url,
                'method': r.request.method,
                'headers': self.redact_auth_hdrs(r.request.headers),
                'body': r.request.body,
                }}
        try:
            data['json'] = r.json()
        except:  # throws unknown exception, differs from documentation
            try:
                data['text'] = r.text
            except:  # maybe a decoding failure is possible, not seen yet
                None
            data['content'] = r.content
        return '---\n' + yaml.dump(self.redact_content(data))

    def log(self, method, path, args, r):
        self.logfile.write(self.format_request(method, path, args, r))

    def call(self, method, path, **kwargs):
        if len(path) > 0 and path[0] != '/':
            raise ValueError('Path has to start with /')
        r = requests.request(method, self.url + path, **kwargs)
        if self.logfile:
            self.log(method, path, kwargs, r)
        return r

    def get(self, path, **kwargs):
        return self.call('GET', path, **kwargs)

    def put(self, path, **kwargs):
        return self.call('PUT', path, **kwargs)

    def post(self, path, **kwargs):
        return self.call('POST', path, **kwargs)

    def patch(self, path, **kwargs):
        return self.call('PATCH', path, **kwargs)

    def check(self, method, path, **kwargs):
        r = self.call(method, path, **kwargs)
        if r.ok:
            return r
        raise APIError('%s %s %i %s' % (path, method, r.status_code, r.reason))

    def check_get(self, path, **kwargs):
        return self.check('GET', path, **kwargs)

    def check_put(self, path, **kwargs):
        return self.check('PUT', path, **kwargs)

    def check_post(self, path, **kwargs):
        return self.check('POST', path, **kwargs)

    def check_patch(self, path, **kwargs):
        return self.check('PATCH', path, **kwargs)

    def check_exists(self, path, **kwargs):
        r = self.get(path, **kwargs)  # Some gitea endpoints don't like HEAD request
        if r.status_code == 404:
            return False
        if r.ok:
            return r
        raise APIError('%s exists %i %s' % (path, r.status_code, r.reason))
