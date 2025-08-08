from obsapi.teaapi import TeaAPI, APIError
from threading import Thread
import http.server
import tempfile
import unittest
import shutil
import json
import yaml
import os

class TestRequest(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.do_request()
    def do_PUT(self):
        self.do_request()
    def do_PATCH(self):
        self.do_request()
    def do_POST(self):
        self.do_request()
    def do_request(self):
        data = self.server.data[self.server.index]
        self.server.index += 1
        if data['request']['method'] != self.command:
            raise TypeError('Expected %s but got %s' % (data['request']['method'], self.command))
        if not self.path.startswith(data['path']):
            raise ValueError('Expected %s but got %s' % (data['path'], self.path))
        if not data['url'].endswith(self.path):
            raise ValueError('Expected %s but got %s' % (data['url'], self.path))
        body = None
        if 'Content-Length' in self.headers:
            body = self.rfile.read(int(self.headers['Content-Length']))
        if data['request']['body'] != body and 'Content-Type' in self.headers and self.headers['Content-Type'] == 'application/json':
            body = json.dumps(json.loads(body.decode()), sort_keys=True).encode()  # At least on SLE12 the order is random
        if data['request']['body'] != body:
            raise ValueError('Expected %s but got %s' %(data['request']['body'], body))

        body = None
        if 'json' in data:
            body = json.dumps(data['json'])
        elif 'text' in data:
            body = data['text']
        elif 'content' in data:
            body = data['content']
        if body:
            body = body.encode()
            self.send_response(data['code'], data['reason'])
            self.send_header('Content-Length', len(body))
            if 'Content-Type' in data['headers']:
                self.send_header('Content-Type', data['headers']['Content-Type'])
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        else:
            self.send_error(data['code'], data['reason'])


class TestServer(http.server.HTTPServer):
    def __init__(self, address, requast, data):
        self.index = 0
        with open(data, 'rb') as f:
            self.data = list(yaml.load_all(f, Loader=yaml.SafeLoader))
        super().__init__(address, requast)

class ServerThread():
    def __init__(self, data):
        self.httpd = TestServer(('', 0), TestRequest, data)

    def url(self):
        return 'http://127.0.0.1:%i' % (self.httpd.server_address[1],)

    def start_server(self, configfile):
        with open(configfile, 'w') as f:
            f.write(yaml.dump( { 'logins': [ { 'name': self.url(), 'url': self.url(), 'token': 'bogon' }]}))
        def _start_server(self):
            while self.httpd.index < len(self.httpd.data):
                self.httpd.handle_request()
        thread = Thread(target=_start_server, args=(self,))
        thread.daemon = True
        thread.start()

    def stop_server(self):
        self.httpd.server_close()

    def __del__(self):
        self.stop_server()

class TestTea(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config = os.path.join(self.tmpdir.name, 'config.yml')

    def tearDown(self):
        self.config = None
        self.tmpdir.cleanup()
        self.tmpdir = None

    def test_gitattr_up_to_date(self):
        st = ServerThread('tests/api/gitattr_up_to_date')
        st.start_server(self.config)
        api = TeaAPI(st.url(), config=self.config)
        api.update_gitattr('michals', 'testrepo', 'testbranch')

    def test_gitattr_nonexistent_file(self):
        st = ServerThread('tests/api/gitattr_nonexistent_file')
        st.start_server(self.config)
        api = TeaAPI(st.url(), config=self.config)
        api.update_gitattr('michals', 'testrepo', 'testbranch')

    def test_gitattr_needs_update(self):
        st = ServerThread('tests/api/gitattr_needs_update')
        st.start_server(self.config)
        api = TeaAPI(st.url(), config=self.config)
        api.update_gitattr('michals', 'testrepo', 'testbranch')

    def test_gitattr_nonexistent_repo(self):
        st = ServerThread('tests/api/gitattr_nonexistent_repo')
        st.start_server(self.config)
        api = TeaAPI(st.url(), config=self.config)
        with self.assertRaisesRegex(APIError, '/api/v1/repos/michals/testrepo/contents/.gitattributes POST 404 Not Found'):
            api.update_gitattr('michals', 'testrepo', 'testbranch')
