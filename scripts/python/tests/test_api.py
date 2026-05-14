from obsapi.teaapi import TeaAPI, json_custom_dump, update_maintainership, get_maintainership
from kutil.config import get_package_archs, get_kernel_projects, uniq
from obsapi.obsapi import OBSAPI, PkgRepo, process_scmsync
from obsapi.uploader import UploaderBase
import xml.etree.ElementTree as ET
from difflib import unified_diff
from obsapi.api import APIError
from threading import Thread
import email.message
import configparser
import urllib.parse
import email.policy
import http.cookies
import http.server
import tempfile
import unittest
import random
import base64
import shutil
import types
import json
import yaml
import bz2
import ssl
import sys
import os

def cookies_to_dict(cookies):
    res = {}
    for k in cookies.keys():
        res[k] = cookies[k].value
    return res

class TestRequest(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.do_request()
    def do_PUT(self):
        self.do_request()
    def do_PATCH(self):
        self.do_request()
    def do_DELETE(self):
        self.do_request()
    def do_POST(self):
        self.do_request()
    def do_HEAD(self):
        self.do_request()

    def do_request(self):
        data = self.server.data[self.server.index]
        self.server.index += 1
        self.check_request(data)
        self.send_reply(data)

    def check_request(self, data):
        if data['method'] != self.command:
            raise TypeError('Expected %s but got %s' % (data['request']['method'], self.command))
        parsed_path = urllib.parse.urlparse(self.path)
        parsed_url = urllib.parse.urlparse(data['url'])
        if parsed_url.path != parsed_path.path:
            raise ValueError('Expected path %s but got %s' % (parsed_url.path, parsed_path.path))
        if parsed_url.params != parsed_path.params:
            raise ValueError('Expected params %s but got %s' % (parsed_url.params, parsed_path.params))
        if parsed_url.fragment != parsed_path.fragment:
            raise ValueError('Expected fragment %s but got %s' % (parsed_url.fragment, parsed_path.fragment))
        if urllib.parse.parse_qs(parsed_url.query) != urllib.parse.parse_qs(parsed_path.query):
            raise ValueError('Expected query %s but got %s' % (parsed_url.query, parsed_path.query))
        req_headers = email.message.EmailMessage(policy=email.policy.HTTP)
        req_headers.update(data['request']['headers'])
        req_headers.update(data['request']['unredirected_hdrs'])

        for hdr in ['Content-type']:
            if req_headers.get(hdr, None) != self.headers.get(hdr, None):
                raise ValueError('Expected %s %s but got %s' % (hdr, req_headers.get(hdr, None), self.headers.get(hdr, None)))
        if 'Authorization' in req_headers and 'Authorization' not in self.headers:
            raise ValueError('Authorization expected but not sent')
        if 'Authorization' not in req_headers and 'Authorization' in self.headers:
            raise ValueError('Authorization not expected but sent')
        if 'Cookie' in req_headers:
            if not 'Cookie' in self.headers:
                raise ValueError('Cookies expected but none sent')
            sent_cookies = cookies_to_dict(http.cookies.SimpleCookie(self.headers['Cookie']))
            if not hasattr(self, 'cookies'):
                # client started off with sending cookies, assume correct cookies loaded from file
                self.cookies = sent_cookies
            else:
                ref_cookies = cookies_to_dict(http.cookies.SimpleCookie(req_headers['Cookie']))
                if list(ref_cookies.keys()) != list(sent_cookies.keys()):
                    raise ValueError("Expected cookies %s but got %s"
                                     % (list(ref_cookies.keys()), list(sent_cookies.keys())))
                for k in sent_cookies.keys():
                    if self.cookies[k] != sent_cookies[k]:
                        raise ValueError("Expected %s cookie value %s but got %s"
                                         % (k, self.cookies[k], sent_cookies[k]))
        body = None
        if 'Content-Length' in self.headers:
            body = self.rfile.read(int(self.headers['Content-Length']))
        if sys.version_info.major == 3 and sys.version_info.minor < 6 and 'Content-Type' in self.headers and self.headers['Content-Type'] == 'application/json':
            body = json.dumps(json.loads(body.decode()), sort_keys=True).encode()  # At least on SLE12 the order is random
            data['request']['body'] = json.dumps(json.loads(data['request']['body'].decode()), sort_keys=True).encode()
        if data['request']['body'] != body:
            raise ValueError('Expected %s but got %s' %(data['request']['body'], body))

    def send_reply(self, data):
        body = None
        if 'json' in data:
            body = json.dumps(data['json'])
        elif 'text' in data:
            body = data['text']
        elif 'content' in data:
            body = data['content']

        self.send_response(data['code'], data['reason'])
        headers = email.message.EmailMessage(policy=email.policy.HTTP)
        for hdr in data['headers']:
            key = list(hdr.keys())[0]
            headers[key] = hdr[key]
        if 'set-cookie' in headers:  # cookies are not saved in the log, generate at random
            cookies = {}
            for c in headers.get_all('set-cookie'):
                cookies.update(cookies_to_dict(http.cookies.SimpleCookie(c)))
            for c in cookies.keys():
                cookies[c] = 'cookie.' + str(random.randrange(1<<53))
            self.cookies = cookies
            for c in cookies.keys():
                if c == '_session_id':  # could also parse flags from the log but domain is bad
                    self.send_header('set-cookie', c + '=' + cookies[c] + '; Path=/; Secure; HttpOnly;')
                else:
                    self.send_header('set-cookie', c + '=' + cookies[c] + '; Path=/; Max-Age=86400; Secure; HttpOnly;')

        for hdr in ['Content-Type', 'www-authenticate', 'location', 'X-Total-Count']:
            if hdr in headers:
                for value in headers.get_all(hdr):
                    self.send_header(hdr, value)
        if body:
            if not isinstance(body, bytes):
                body = body.encode()
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        else:
            self.end_headers()


class TestServer(http.server.HTTPServer):
    def __init__(self, address, requast, data):
        self.index = 0
        with open(data, 'rb') as f:
            self.data = list(yaml.load_all(f, Loader=yaml.SafeLoader))
        super().__init__(address, requast)

class ServerThread():
    def __init__(self, data):
        self.httpd = TestServer(('', 0), TestRequest, data)
        self.httpd.socket = self.get_ssl_context().wrap_socket(self.httpd.socket, server_side=True)

    def get_ssl_context(self):
        if sys.version_info.major == 3 and sys.version_info.minor < 6:  # SLE 12
            self.servercert = 'tests/api/certificate12.pem'
            self.serverkey = 'tests/api/certkey12.pem'
        else:
            self.servercert = 'tests/api/certificate.pem'
            self.serverkey = 'tests/api/certkey.pem'

        if hasattr(ssl, 'PROTOCOL_TLS_SERVER'):
            proto = ssl.PROTOCOL_TLS_SERVER
        else:
            proto = ssl.PROTOCOL_TLSv1_2
        context = ssl.SSLContext(proto)
        context.load_cert_chain(self.servercert, self.serverkey)
        try:
            context.set_ciphers("@SECLEVEL=1:ALL")
        except ssl.SSLError:  # not available on SLE12
            None
        return context

    def url(self):
        return 'https://127.0.0.1:%i' % (self.httpd.server_address[1],)

    def start_server(self, teaconfig=None, obsconfig=None):
        if teaconfig:
            with open(teaconfig, 'w') as f:
                f.write(yaml.dump( { 'logins': [ { 'name': self.url(), 'url': self.url(), 'token': 'bogon' }]}))
        if obsconfig:
            config = configparser.ConfigParser(delimiters=('='), interpolation=None)
            config[self.url()] = { 'user': 'obsuser', 'pass': 'obspassword' }
            with open(obsconfig, 'w') as f:
                config.write(f)

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

    data_consumed = property(lambda self: self.httpd.index == len(self.httpd.data))


class TestMisc(unittest.TestCase):
    def test_json_dump(self):
        testdata = [
                [
                    { 'A': ['b', 'c', 'd'], 'E': ['f'], 'G': [], 'H': None },
'''{
  "A": [ "b","c","d" ],
  "E": [ "f" ],
  "G": [  ],
  "H": null
}
'''
],
                [ {}, '''{
}
'''
                 ],
                [ {'header': {'document': 'obs-maintainers', 'version': '1.0'}, 'project': {'users': ['project_owner1', 'project_owner2'], 'groups': ['project-maintainer-group']}, 'packages': {'package1': {'users': ['package1-user1-maintainer', 'package1-user2-maintainer']}, 'package2': {'groups': ['package2-group-maintainer']}, 'package3': {'users': ['package3-user-maintainer'], 'groups': ['package3-group1-maintainer', 'package3-group2-maintainer']}}},
                 '''{
  "header": {
    "document": "obs-maintainers",
    "version": "1.0"
  },
  "packages": {
    "package1": {
      "users": [
        "package1-user1-maintainer",
        "package1-user2-maintainer"
      ]
    },
    "package2": {
      "groups": [
        "package2-group-maintainer"
      ]
    },
    "package3": {
      "groups": [
        "package3-group1-maintainer",
        "package3-group2-maintainer"
      ],
      "users": [
        "package3-user-maintainer"
      ]
    }
  },
  "project": {
    "groups": [
      "project-maintainer-group"
    ],
    "users": [
      "project_owner1",
      "project_owner2"
    ]
  }
}
'''
                 ],
                ]
        for data, result in testdata:
            self.assertEqual(json_custom_dump(data), result)

    def test_get_maintainership(self):
        testdata = [
                [[{}, 'kernel-source'], []],
                [[{'header': {}}, 'kernel-source'], []],
                [[{'header': {}, 'packages': {'kernel-source': {'users': ['maint4', 'maint5']}}}, 'kernel-source'], ['maint4', 'maint5']],
                [[{'header': {}, 'packages': {'kernel-source': {'users': None}}}, 'kernel-source'], []],
                [[{'kernel-source': ['maint4', 'maint5']}, 'kernel-source'], ['maint4', 'maint5']],
                ]
        for args, result in testdata:
            self.assertEqual(get_maintainership(*args), result)

    def test_update_maintainership(self):
        testdata = [
                [[{}, 'kernel-source', ['maint1', 'maint2']], {'kernel-source' : ['maint1', 'maint2']}],
                [[{'header': {}}, 'kernel-source', ['maint1', 'maint2']], {'header': {}, 'packages': {'kernel-source': {'users': ['maint1', 'maint2']}}}],
                [[{'header': {}, 'packages': {'kernel-source': {'users': ['maint4', 'maint5']}}}, 'kernel-source', ['maint1', 'maint2']], {'header': {}, 'packages': {'kernel-source': {'users': ['maint1', 'maint2']}}}],
                ]
        for args, result in testdata:
            self.assertEqual(update_maintainership(*args), result)

    def test_uniq(self):
        testdata = [
                [
                    ['a', 'c' ,'b' ,'a', 'f', 'e'],
                    ['a', 'c' ,'b' ,'f', 'e'],
                    ],
                [
                    ['a', 'c' ,'b' ,'a', 'f', 'b'],
                    ['a', 'c' ,'b' ,'f'],
                    ],
                ]
        for data, result in testdata:
            self.assertEqual(uniq(data), result)

    def test_process_scmsync(self):
        testdata = [
                [urllib.parse.urlparse('https://src.suse.de/org/repo?trackingbranch=branch#' + 'cafedead' * 8),
                 PkgRepo(api='https://src.suse.de', org='org', repo='repo', branch='branch', commit='cafedead' * 8)],
                [urllib.parse.urlparse('https://src.suse.de/org/repo?trackingbranch=branch#' + 'cafedead' * 5),
                 PkgRepo(api='https://src.suse.de', org='org', repo='repo', branch='branch', commit='cafedead' * 5)],
                [urllib.parse.urlparse('https://src.suse.de/org/repo#' + 'cafedead' * 8),
                 PkgRepo(api='https://src.suse.de', org='org', repo='repo', branch=None, commit='cafedead' * 8)],
                [urllib.parse.urlparse('https://src.suse.de/org/repo#' + 'branch'),
                 PkgRepo(api='https://src.suse.de', org='org', repo='repo', branch='branch', commit=None)],
                ]
        testexcept = [
                urllib.parse.urlparse('https://src.suse.de/org/repo?trackingbranch=' + 'branch'),
                urllib.parse.urlparse('https://src.suse.de/org/repo?trackingbranch=foo#' + 'bar'),
                urllib.parse.urlparse('https://src.suse.de/org/repo?trackingbranch=branch#' + 'cafedead' * 6),
                urllib.parse.urlparse('https://src.suse.de/org/repo'),
                ]
        for data, result in testdata:
            self.assertEqual(process_scmsync(data), result)
        for data in testexcept:
            self.assertRaises(Exception)

class APITest(unittest.TestCase):
    def log_cycle(self, test_fn, orig_log):
        tmpdir = tempfile.TemporaryDirectory()
        new_log = os.path.join(tmpdir.name, 'new_log')
        test_fn(orig_log, new_log)
        self.tearDown()
        self.setUp()
        test_fn(new_log, None)
        tmpdir.cleanup()


class TestTea(APITest):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config = os.path.join(self.tmpdir.name, 'config.yml')

    def tearDown(self):
        self.config = None
        self.tmpdir.cleanup()
        self.tmpdir = None

    def test_config_search(self):
        st = ServerThread('tests/api/user')
        st.start_server(teaconfig=self.config)
        os.environ['HOME'] = self.tmpdir.name
        with self.assertRaisesRegex(RuntimeError, '^Error loading gitea-tea configuration file .*[.]config/tea/config.yml:'):
            api = TeaAPI(st.url(), ca=st.servercert)
        os.makedirs(os.path.join(self.tmpdir.name, '.config/tea'), exist_ok=True)
        home_config = os.path.join(self.tmpdir.name, '.config/tea/config.yml')
        shutil.copy('tests/api/binary_garbage', home_config)
        with self.assertRaisesRegex(RuntimeError, '^Error loading gitea-tea configuration file .* unacceptable character'):
            api = TeaAPI(st.url(), ca=st.servercert)
        shutil.copy('/dev/null', home_config)
        with self.assertRaisesRegex(RuntimeError, '^Error loading gitea-tea configuration file .* gitea-tea configuration is expected to be a dictionary'):
            api = TeaAPI(st.url(), ca=st.servercert)
        with open(self.config, 'r') as f:
            config = yaml.safe_load(f)
        config['logins'][0]['url'] = 'foobar'
        with open(home_config, 'w') as f:
            yaml.dump(config, f)
        with self.assertRaisesRegex(RuntimeError, '^Cannot find gitea-tea [(]tea-cli[)] configuration for https://127.0.0.1:'):
            api = TeaAPI(st.url(), ca=st.servercert)
        shutil.copy(self.config, home_config)
        api = TeaAPI(st.url(), ca=st.servercert)
        self.assertEqual(api.get_user(), 'michals')
        self.assertTrue(st.data_consumed)

    def test_url_trailing_slash(self):
        st = ServerThread('tests/api/user')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url() + '/', config=self.config, ca=st.servercert)
        self.assertEqual(api.get_user(), 'michals')
        self.assertTrue(st.data_consumed)

    def test_config_trailing_slash(self):
        st = ServerThread('tests/api/user')
        st.start_server(teaconfig=self.config)
        with open(self.config, 'r') as f:
            config = yaml.safe_load(f)
        config['logins'][0]['url'] = config['logins'][0]['url'] + '/'
        with open(self.config, 'w') as f:
            yaml.dump(config, f)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        self.assertEqual(api.get_user(), 'michals')
        self.assertTrue(st.data_consumed)

    def test_getuser(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            self.assertEqual(api.get_user(), 'michals')
            self.assertTrue(st.data_consumed)
            st.stop_server()
            self.assertEqual(api.get_user(), 'michals')  # cached value, no server comm
        self.log_cycle(test_fn, 'tests/api/user')

    def test_list_repos(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            reference = ['kernel-source', 'kernel-livepatch-MICRO-6-0-RT_Update_10', 'kernel-livepatch-MICRO-6-0-RT_Update_11', 'kernel-livepatch-MICRO-6-0-RT_Update_12', 'kernel-livepatch-MICRO-6-0-RT_Update_4', 'kernel-livepatch-MICRO-6-0-RT_Update_5', 'kernel-livepatch-MICRO-6-0-RT_Update_6', 'kernel-livepatch-MICRO-6-0-RT_Update_7', 'kernel-livepatch-MICRO-6-0-RT_Update_8', 'kernel-livepatch-MICRO-6-0-RT_Update_9', 'kernel-livepatch-MICRO-6-0_Update_10', 'kernel-livepatch-MICRO-6-0_Update_11', 'kernel-livepatch-MICRO-6-0_Update_12', 'kernel-livepatch-MICRO-6-0_Update_13', 'kernel-livepatch-MICRO-6-0_Update_4', 'kernel-livepatch-MICRO-6-0_Update_5', 'kernel-livepatch-MICRO-6-0_Update_6', 'kernel-livepatch-MICRO-6-0_Update_7', 'kernel-livepatch-MICRO-6-0_Update_8', 'kernel-livepatch-MICRO-6-0_Update_9', 'kgraft-patch-SLE12-SP5_Update_64', 'kgraft-patch-SLE12-SP5_Update_65', 'kgraft-patch-SLE12-SP5_Update_66', 'kgraft-patch-SLE12-SP5_Update_67', 'kgraft-patch-SLE12-SP5_Update_68', 'kgraft-patch-SLE12-SP5_Update_69', 'kgraft-patch-SLE12-SP5_Update_70', 'kgraft-patch-SLE12-SP5_Update_71', 'kgraft-patch-SLE12-SP5_Update_72', 'kgraft-patch-SLE12-SP5_Update_73', 'kgraft-patch-SLE12-SP5_Update_74', 'kgraft-patch-SLE12-SP5_Update_75', 'kernel-livepatch-SLE15-SP4_Update_35', 'kernel-livepatch-SLE15-SP4_Update_36', 'kernel-livepatch-SLE15-SP4_Update_37', 'kernel-livepatch-SLE15-SP4_Update_38', 'kernel-livepatch-SLE15-SP4_Update_39', 'kernel-livepatch-SLE15-SP4_Update_40', 'kernel-livepatch-SLE15-SP4_Update_41', 'kernel-livepatch-SLE15-SP4_Update_42', 'kernel-livepatch-SLE15-SP4_Update_43', 'kernel-livepatch-SLE15-SP4_Update_44', 'kernel-livepatch-SLE15-SP4_Update_45', 'kernel-livepatch-SLE15-SP4_Update_46', 'kernel-livepatch-SLE15-SP4_Update_47', 'kernel-livepatch-SLE15-SP5_Update_22', 'kernel-livepatch-SLE15-SP5_Update_23', 'kernel-livepatch-SLE15-SP5_Update_24', 'kernel-livepatch-SLE15-SP5_Update_25', 'kernel-livepatch-SLE15-SP5_Update_26', 'kernel-livepatch-SLE15-SP5_Update_27', 'kernel-livepatch-SLE15-SP5_Update_28', 'kernel-livepatch-SLE15-SP5_Update_29', 'kernel-livepatch-SLE15-SP5_Update_30', 'kernel-livepatch-SLE15-SP5_Update_31', 'kernel-livepatch-SLE15-SP5_Update_32', 'kernel-livepatch-SLE15-SP5_Update_33', 'kernel-livepatch-SLE15-SP6_Update_10', 'kernel-livepatch-SLE15-SP6_Update_11', 'kernel-livepatch-SLE15-SP6_Update_12', 'kernel-livepatch-SLE15-SP6_Update_13', 'kernel-livepatch-SLE15-SP6_Update_14', 'kernel-livepatch-SLE15-SP6_Update_15', 'kernel-livepatch-SLE15-SP6_Update_16', 'kernel-livepatch-SLE15-SP6_Update_17', 'kernel-livepatch-SLE15-SP6_Update_18', 'kernel-livepatch-SLE15-SP6_Update_7', 'kernel-livepatch-SLE15-SP6_Update_8', 'kernel-source-rt', 'kernel-livepatch-SLE16_Update_3', 'kernel-livepatch-SLE16_Update_2', 'kernel-livepatch-SLFO-Main_Update_0', 'kernel-livepatch-SLFO-Main-RT_Update_0', 'kernel-livepatch-SLE15-SP6_Update_9', 'kernel-livepatch-SLE15-SP7-RT_Update_0', 'kernel-livepatch-SLE15-SP7-RT_Update_1', 'kernel-livepatch-SLE15-SP7-RT_Update_2', 'kernel-livepatch-SLE15-SP7-RT_Update_3', 'kernel-livepatch-SLE15-SP7-RT_Update_4', 'kernel-livepatch-SLE15-SP7-RT_Update_5', 'kernel-livepatch-SLE15-SP7-RT_Update_6', 'kernel-livepatch-SLE15-SP7-RT_Update_7', 'kernel-livepatch-SLE15-SP7_Update_0', 'kernel-livepatch-SLE15-SP7_Update_1', 'kernel-livepatch-SLE15-SP7_Update_2', 'kernel-livepatch-SLE15-SP7_Update_3', 'kernel-livepatch-SLE15-SP7_Update_4', 'kernel-livepatch-SLE15-SP7_Update_5', 'kernel-livepatch-SLE15-SP7_Update_6', 'kernel-livepatch-SLE15-SP7_Update_7', 'kernel-livepatch-SLE16-RT_Update_0', 'kernel-livepatch-SLE16-RT_Update_1', 'kernel-livepatch-SLE16-RT_Update_2', 'kernel-livepatch-SLE16-RT_Update_3', 'kernel-livepatch-SLE16_Update_0', 'kernel-livepatch-SLE16_Update_1', 'kernel-source-longterm', 'kernel-source-vanilla', 'kernel-livepatch-MICRO-6-0-RT_Update_2', 'kernel-livepatch-MICRO-6-0-RT_Update_3', 'kernel-livepatch-MICRO-6-0_Update_2', 'kernel-livepatch-MICRO-6-0_Update_3', 'kgraft-patch-SLE12-SP5_Update_76', 'kernel-livepatch-SLE15-SP4_Update_48', 'kernel-livepatch-SLE15-SP5_Update_34', 'kernel-livepatch-SLE15-SP6_Update_19', 'kernel-livepatch-SLE15-SP7-RT_Update_8', 'kernel-livepatch-SLE15-SP7_Update_8', 'kernel-livepatch-SLE16-RT_Update_4', 'kernel-livepatch-SLE16_Update_4', 'SLFO', 'kernel-livepatch-MICRO-6-0-RT_Update_14', 'kernel-livepatch-MICRO-6-0-RT_Update_17', 'kgraft-patch-SLE12-SP5_Update_77', 'kernel-livepatch-SLE15-SP4_Update_49', 'kernel-livepatch-SLE15-SP5_Update_35', 'kernel-livepatch-SLE15-SP6_Update_20', 'kernel-livepatch-SLE15-SP7-RT_Update_9', 'kernel-livepatch-SLE15-SP7_Update_9', 'kernel-livepatch-SLE16-RT_Update_5', 'kernel-livepatch-SLE16_Update_5', 'kernel-livepatch-MICRO-6-0-RT_Update_13', 'kernel-livepatch-MICRO-6-0_Update_14', 'kgraft-patch-SLE12-SP5_Update_78', 'kernel-livepatch-SLE15-SP4_Update_50', 'kernel-livepatch-SLE15-SP5_Update_36', 'kernel-livepatch-SLE15-SP6_Update_21', 'kernel-livepatch-SLE15-SP7-RT_Update_10', 'kernel-livepatch-SLE15-SP7_Update_10', 'kernel-livepatch-SLE16-RT_Update_6', 'kernel-livepatch-SLE16_Update_6', 'SLFO_Kernel', 'kernel-livepatch-MICRO-6-0-RT_Update_15', 'kernel-livepatch-MICRO-6-0-RT_Update_19', 'kgraft-patch-SLE12-SP5_Update_79', 'kernel-livepatch-SLE15-SP5_Update_37', 'kernel-livepatch-SLE15-SP6_Update_22', 'kernel-livepatch-SLE15-SP7-RT_Update_11', 'kernel-livepatch-SLE15-SP7_Update_11', 'kernel-livepatch-SLE16-RT_Update_7', 'kernel-livepatch-SLE16_Update_7', 'kernel-livepatch-MICRO-6-0-RT_Update_18', 'kernel-livepatch-MICRO-6-0_Update_16', 'kernel-livepatch-MICRO-6-0_Update_17', 'kernel-livepatch-MICRO-6-0_Update_18']
            if sys.version_info.major == 3 and sys.version_info.minor < 6:
                self.assertEqual(sorted(list(api.list_repos('kernelbugs').keys())), sorted(reference))
            else:
                self.assertEqual(list(api.list_repos('kernelbugs').keys()), reference)
            self.assertTrue(st.data_consumed)
            st.stop_server()
        self.log_cycle(test_fn, 'tests/api/list_repos')

    def test_gitattr_up_to_date(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.update_gitattr('michals', 'testrepo', 'testbranch')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/gitattr_up_to_date')

    def test_file_up_to_date(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.update_file('michals', 'testrepo', 'testbranch', '.gitattributes', '''*.tar.?z filter=lfs diff=lfs merge=lfs -text
foobar
*.tar.bz2 filter=lfs diff=lfs merge=lfs -text
''')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/gitattr_up_to_date')

    def test_gitattr_nonexistent_file(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.update_gitattr('michals', 'testrepo', 'testbranch')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/gitattr_nonexistent_file')

    def test_file_nonexistent(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.update_file('michals', 'testrepo', 'testbranch', '.gitattributes', '''*.tar.bz2 filter=lfs diff=lfs merge=lfs -text
*.tar.?z filter=lfs diff=lfs merge=lfs -text
''')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/gitattr_nonexistent_file')

    def test_gitattr_needs_update(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.update_gitattr('michals', 'testrepo', 'testbranch')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/gitattr_needs_update')

    def test_file_needs_update(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.update_file('michals', 'testrepo', 'testbranch', '.gitattributes', '''*.tar.?z filter=lfs diff=lfs merge=lfs -text
foobar
*.tar.bz2 filter=lfs diff=lfs merge=lfs -text
''')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/gitattr_needs_update')

    def test_file_needs_update_incomplete(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.update_file('michals', 'testrepo', 'testbranch', '.gitattributes', '''*.tar.?z filter=lfs diff=lfs merge=lfs -text
foobar''')
            self.assertEqual(st.data_consumed, not outlog)  # the refreshed log now reflects the actual operation
        self.log_cycle(test_fn, 'tests/api/gitattr_needs_update')

    def test_gitattr_nonexistent_repo(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            with self.assertRaisesRegex(APIError, '/api/v1/repos/michals/testrepo/contents/.gitattributes POST 404 Not Found'):
                api.update_gitattr('michals', 'testrepo', 'testbranch')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/gitattr_nonexistent_repo')

    def test_content_update(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.update_content('michals', 'testrepo', 'testbranch', 'tests/api/content/update', 'Update flies')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/update_content')

    def test_create_or_reset_branch(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.create_or_reset_branch('michals', 'testrepo', 'downstream', 'testbranch', '60298bc4bf915a41f8f16f64d05a4125b434ca63112c53ba6779b039123c6db6', True)
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/branch_new')

        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.create_or_reset_branch('michals', 'testrepo', 'downstream', 'testbranch', '60298bc4bf915a41f8f16f64d05a4125b434ca63112c53ba6779b039123c6db6', True)
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/branch_up_to_date')

        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.create_or_reset_branch('michals', 'testrepo', 'downstream', 'testbranch', 'a0156cd1f6cc836cec02b406a8c5154311bcd800e431a4092e5b59f611049ee4', False)
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/branch_no_roll')

        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(teaconfig=self.config)
            api = TeaAPI(st.url(), config=self.config, ca=st.servercert, logfile=outlog)
            api.create_or_reset_branch('michals', 'testrepo', 'downstream', 'testbranch', 'a0156cd1f6cc836cec02b406a8c5154311bcd800e431a4092e5b59f611049ee4', True)
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/branch_roll_forward')


class TestOBS(APITest):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config = os.path.join(self.tmpdir.name, 'oscrc')
        self.cookiejar = os.path.join(self.tmpdir.name, 'cookiejar')
        st = ServerThread('tests/api/obsapi_log_in')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        api.check_login()
        self.assertTrue(st.data_consumed)

    def tearDown(self):
        self.config = None
        self.tmpdir.cleanup()
        self.tmpdir = None

    def test_config_search(self):
        st = ServerThread('tests/api/obsapi_basic')
        st.start_server(obsconfig=self.config)
        os.environ['HOME'] = self.tmpdir.name
        with self.assertRaisesRegex(RuntimeError, '^Could not find an osc configuration file in .*[.]oscrc .*[.]config/osc/oscrc'):
            api = OBSAPI(st.url(), ca=st.servercert)
        os.makedirs(os.path.join(self.tmpdir.name, '.config/osc'), exist_ok=True)
        home_config = os.path.join(self.tmpdir.name, '.config/osc/oscrc')
        shutil.copy('tests/api/binary_garbage', home_config)
        with self.assertRaisesRegex(RuntimeError, '^Error loading osc configuration file .*[.]config/osc/oscrc .* codec can\'t decode byte'):
            api = OBSAPI(st.url(), ca=st.servercert)
        shutil.copy('/dev/null', os.path.join(self.tmpdir.name, '.oscrc'))
        with self.assertRaisesRegex(RuntimeError, '^No configuration for API https://127.0.0.1:'):
            api = OBSAPI(st.url(), ca=st.servercert)
        shutil.copy(self.config, os.path.join(self.tmpdir.name, '.oscrc'))
        os.makedirs(os.path.join(self.tmpdir.name, '.local/state/osc'), exist_ok=True)
        home_cookiejar = os.path.join(self.tmpdir.name, '.local/state/osc/cookiejar')
        shutil.copy('tests/api/binary_garbage', home_cookiejar)
        with self.assertRaisesRegex(RuntimeError, '^Error loading cookies: .* codec can\'t decode byte'):
            api = OBSAPI(st.url(), ca=st.servercert)
        shutil.copy(self.cookiejar, home_cookiejar)
        api = OBSAPI(st.url(), ca=st.servercert)
        api.check_login()
        self.assertTrue(st.data_consumed)

    def test_config_passw(self):
        st = ServerThread('tests/api/obsapi_basic')
        st.start_server(obsconfig=self.config)
        os.environ['HOME'] = self.tmpdir.name
        os.makedirs(os.path.join(self.tmpdir.name, '.config/osc'), exist_ok=True)
        home_config = os.path.join(self.tmpdir.name, '.config/osc/oscrc')
        config = configparser.ConfigParser(delimiters=('='), interpolation=None, default_section=None)
        config.read(self.config)
        section_name = config.sections()[0]
        config.remove_option(section_name, 'user')
        with open(home_config, 'w') as f:
            config.write(f)
        with self.assertRaisesRegex(RuntimeError, '^No username found for API https://127.0.0.1:'):
            api = OBSAPI(st.url(), ca=st.servercert)
        config.read(self.config)
        passw = config.get(section_name, 'pass')
        passw_obfuscated = base64.standard_b64encode(bz2.compress(passw.encode())).decode()
        config.remove_option(section_name, 'pass')
        with open(home_config, 'w') as f:
            config.write(f)
        with self.assertRaisesRegex(RuntimeError, '^No password found for API https://127.0.0.1:.*/.config/osc/oscrc. Authentication type None not supported.'):
            api = OBSAPI(st.url(), ca=st.servercert)
        config.set(section_name, 'credentials_mgr_class', 'foobar')
        with open(home_config, 'w') as f:
            config.write(f)
        with self.assertRaisesRegex(RuntimeError, '^No password found for API https://127.0.0.1:.*/.config/osc/oscrc. Authentication type foobar not supported.'):
            api = OBSAPI(st.url(), ca=st.servercert)
        config.remove_option(section_name, 'credentials_mgr_class')
        config.set(section_name, 'passx', passw_obfuscated)
        with open(home_config, 'w') as f:
            config.write(f)
        api = OBSAPI(st.url(), ca=st.servercert)
        self.assertEqual(api.passw, passw)
        config.remove_option(section_name, 'passx')
        config.set(section_name, 'credentials_mgr_class', 'osc.credentials.ObfuscatedConfigFileCredentialsManager')
        config.set(section_name, 'pass', passw_obfuscated)
        with open(home_config, 'w') as f:
            config.write(f)
        api = OBSAPI(st.url(), ca=st.servercert)
        self.assertEqual(api.passw, passw)
        config.remove_option(section_name, 'credentials_mgr_class')
        config.read(self.config)
        with open(home_config, 'w') as f:
            config.write(f)
        api = OBSAPI(st.url(), ca=st.servercert)
        self.assertEqual(api.passw, passw)

    def test_url_trailing_slash(self):
        st = ServerThread('tests/api/obsapi_basic')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url() + '/', config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        api.check_login()
        self.assertTrue(st.data_consumed)

    def test_config_trailing_slash(self):
        st = ServerThread('tests/api/obsapi_basic')
        st.start_server(obsconfig=self.config)
        config = configparser.ConfigParser(delimiters=('='), interpolation=None, default_section=None)
        config.read(self.config)
        section_name = config.sections()[0]
        config.add_section(section_name + '/')
        for opt, value in config.items(section_name):
            config.set(section_name + '/', opt, value)
        config.remove_section(section_name)
        with open(self.config, 'w') as f:
            config.write(f)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        api.check_login()
        self.assertTrue(st.data_consumed)

    def test_basic(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            api.check_login()
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_basic')

    def test_SSL(self):
        st = ServerThread('tests/api/obsapi_basic')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar)
        with self.assertRaisesRegex(Exception, 'certificate verify failed'):
            api.check_login()
        self.assertFalse(st.data_consumed)

    def test_log_in(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            os.unlink(self.cookiejar)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            api.check_login()
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_log_in')

    def copy_key(self):
        # permissions not stored exactly in git, ssh refuses to read 644 files
        key = os.path.join(self.tmpdir.name, 'testkey')
        shutil.copy('tests/api/testkey', key)
        os.chmod(key, 0o400)
        shutil.copy('tests/api/testkey.pub', os.path.join(self.tmpdir.name, 'testkey.pub'))
        config = configparser.ConfigParser(delimiters=('='), interpolation=None)
        config.read(self.config)
        config[config.sections()[0]]['sshkey'] = os.path.abspath(key)
        with open(self.config, 'w') as f:
            config.write(f)
        return key

    def test_sig(self):
        st = ServerThread('/dev/null')
        st.start_server(obsconfig=self.config)  # Part of configuration only happens when starting the server
        st.stop_server()
        self.copy_key()
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        self.assertEqual(api.ssh_signature(1755779838, api.user, api.sshkey, 'some realm'),
                         'keyId="obsuser",algorithm="ssh",headers="(created)",created=1755779838,signature="U1NIU0lHAAAAAQAAADMAAAALc3NoLWVkMjU1MTkAAAAge7Wj9uPdUE8nqD2mPJ8R9tZLZ2Wgwqj1MT7sJlFhJj4AAAAKc29tZSByZWFsbQAAAAAAAAAGc2hhNTEyAAAAUwAAAAtzc2gtZWQyNTUxOQAAAEBNMTVv/cHwZMLNZ2UaNaVUX2fJw8J4LvTCcHTrpXQ2z2pr5ldM+UvKypyBExf42plNYEI3hw59V4Uzej/di5YA"')

    def test_Y(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            os.unlink(self.cookiejar)
            self.copy_key()
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            api.check_login()
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_log_in_ssh')

    def test_missing_key(self):
        st = ServerThread('/dev/null')
        st.start_server(obsconfig=self.config)
        st.stop_server()
        key = self.copy_key()
        os.unlink(key)
        with self.assertRaisesRegex(RuntimeError, '^Key file does not exist'):
                OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)

    def test_invalid_key(self):
        st = ServerThread('tests/api/obsapi_log_in_ssh')
        st.start_server(obsconfig=self.config)
        key = self.copy_key()
        os.truncate(key, 0)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        with self.assertRaisesRegex(RuntimeError, '^Failed to create a SSH signature$'):
            api.check_login()
        self.assertFalse(st.data_consumed)

    def test_not_configured_key(self):
        st = ServerThread('tests/api/obsapi_log_in_ssh')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        if sys.version_info.major == 3 and sys.version_info.minor < 6:
            re = '''^Authentication required but no usable credentials found
Requested authorizarion:'''
        else:
            re = '''^Authentication required but no usable credentials found
Requested authorizarion: {'signature': {'realm': 'Use your developer account', 'headers': '[(]created[)]'}}
Available credentials:  password: True  SSH key: False$'''
        with self.assertRaisesRegex(RuntimeError, re):
            api.check_login()
        self.assertFalse(st.data_consumed)

    def test_pkgrepo(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            self.assertEqual(api.package_repo('SUSE:SLFO:1.2', 'kernel-source-azure'),
                             PkgRepo(api='https://src.suse.de', org='pool', repo='kernel-source-azure', branch='slfo-1.2',
                                     commit='b20dbdf296c74a2897e61205e5c9edcb7f85340ede6bbfd18c05dbfce87c267b'))
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_pkgrepo')

    def test_pkgrepo_default(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            self.assertEqual(api.package_repo('SUSE:SLE-15-SP7:GA', 'kernel-source-azure'),
                             PkgRepo(api=st.url(), org='pool', repo='kernel-source-azure', branch=None, commit=None))
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_pkgrepo_no_scmsync')

        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            self.assertEqual(api.package_repo('SUSE:SLFO:1.2', 'kernel-source-foobar'),
                             PkgRepo(api=st.url(), org='pool', repo='kernel-source-foobar', branch=None, commit=None))
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_pkgrepo_nonexistent_pkg')

    def test_project_exists(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            self.assertTrue(api.project_exists('Kernel:HEAD'))
            self.assertFalse(api.project_exists('nonexistent'))
        self.log_cycle(test_fn, 'tests/api/obsapi_project_exists')

    def test_list_projects(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            self.assertEqual(api.list_projects(),
                    ['AlmaLinux:10', 'AlmaLinux:8', 'AlmaLinux:9', 'Alpine:Edge', 'Alpine:Latest', 'Amazon:AL2023', 'Apache', 'Apache:MirrorBrain', 'Apache:MirrorBrain:development', 'Apache:Modules', 'zypp:SLE-15-SP7-Branch', 'zypp:TEST', 'zypp:TW', 'zypp:ci', 'zypp:ci:libzypp', 'zypp:ci:zypper', 'zypp:jezypp', 'zypp:jezypp:SuSE-RES-8-Branch', 'zypp:jezypp:SuSE-RES-9-Branch', 'zypp:plugins'])
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_list_projects')

    def test_list_packages(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            self.assertEqual(api.list_project_packages('Kernel:tools'),
                    ['ShellCheck', 'bash-git-prompt', 'bison', 'boottest-ramdisk', 'boottest-ramdisk-12', 'boottest-ramdisk-15', 'boottest-ramdisk-16', 'boottest-ramdisk-16.ARM', 'boottest-ramdisk-16.PowerPC', 'capstone', 'container-base', 'cross-aarch64-gcc48', 'cross-armv7hl-gcc48', 'cross-binutils', 'cross-gcc13', 'cross-gcc14', 'cross-gcc15', 'cross-gcc48', 'cross-gcc7', 'cross-ia64-gcc48', 'cross-ppc64-gcc48', 'cross-ppc64le-gcc48', 'cross-s390x-gcc48', 'cross-x86_64-gcc48', 'dwarves.Factory', 'elfutils', 'elfutils.Factory', 'gcc13', 'gcc13.build', 'gcc14', 'gcc14.build', 'gcc15', 'gcc48', 'gcc6', 'gcc7.build', 'git', 'git-credential-oauth', 'git-fixes', 'git-lfs', 'go1.12', 'go1.14', 'go1.4', 'golang-github-cpuguy83-go-md2man', 'golang-packaging', 'grub2', 'http-parser', 'kbuild-gcc', 'kbuild-support', 'kcov', 'kernel-install-tools', 'kernel-obs-build', 'kernel-source-component', 'libcontainers-common', 'libgit2', 'libgit2.1.7', 'libgit2.1.9', 'libssh2_org', 'liburing2', 'lua-alt-getopt', 'lua-argparse', 'lua-busted', 'lua-cliargs', 'lua-compat-5.3', 'lua-dkjson', 'lua-inspect', 'lua-jsregexp', 'lua-ldoc', 'lua-loadkit', 'lua-lpeg', 'lua-lua-ev', 'lua-luacheck', 'lua-luafilesystem', 'lua-luarocks', 'lua-luassert', 'lua-luasystem', 'lua-luaterm', 'lua-macros', 'lua-markdown', 'lua-mediator_lua', 'lua-moonscript', 'lua-penlight', 'lua-say', 'lua-serpent', 'lua-shell-games', 'lua-tl', 'lua53', 'lua54', 'memory-constraints', 'obs-service-kiwi_metainfo_helper', 'patchtools', 'perl-Text-Markdown', 'pesign-obs-integration', 'python-augeas', 'python-augeas.3.11', 'python-cffi', 'python-mypy', 'python-pygit2', 'python-pygit2.3.11', 'python-typed-ast', 'python36', 'qemu', 'quickjs', 'quilt', 'rapidquilt', 'rpmdevtools', 'rust', 'skopeo', 'suse-add-cves', 'suse-get-maintainers', 'suse-kabi-tools', 'uki-tool', 'umoci', 'zstd'])
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_list_packages')

    def test_list_links(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            self.assertEqual(api.list_package_links('Kernel:SLE15-SP7', 'kernel-source'),
                    ['dtb-aarch64', 'kernel-64kb', 'kernel-default', 'kernel-docs', 'kernel-kvmsmall', 'kernel-obs-build', 'kernel-obs-qa', 'kernel-syms', 'kernel-zfcpdump'])
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_list_links')

    def test_binary_file(self):
        with open('tests/api/binary_garbage', 'rb') as f:
            data = f.read()
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            self.assertEqual(api.file_exists('home:michals', 'vertest', 'binary_garbage').content, data)
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_binary')

        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            api.upload_file('home:michals', 'vertest', 'binary_garbage', data)
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_binary_put')

    def test_create_project(self):
        def test_fn(inlog, outlog):
            st = ServerThread(inlog)
            st.start_server(obsconfig=self.config)
            api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert, logfile=outlog)
            api.create_project('home:michals:kernel-test',
                               conf='Substitute: kernel-dummy\nSubstitute: rpmlint-Factory\nSubstitute: post-build-checks-malwarescan\nMacros:\n%is_kotd 1\n%klp_ipa_clones 1\n%is_kotd_qa (0||("%_repository" == "QA"))\n:Macros\nBuildFlags: excludebuild:kernel-source:kernel-obs-qa\nBuildFlags: excludebuild:kernel-obs-qa\nBuildFlags: nouseforbuild:kernel-source:kernel-obs-build\nBuildFlags: nouseforbuild:kernel-obs-build\n%if 0||("%_repository" == "QA")\nBuildFlags: !excludebuild:kernel-source:kernel-obs-qa\nBuildFlags: !excludebuild:kernel-obs-qa\nBuildFlags: onlybuild:kernel-source:kernel-obs-qa\nBuildFlags: onlybuild:kernel-obs-qa\nBuildFlags: onlybuild:kernel-obs-build.agg\nBuildFlags: onlybuild:nonexistent-package\nBuildFlags: !nouseforbuild:kernel-source:kernel-obs-build\nBuildFlags: !nouseforbuild:kernel-obs-build\n%endif\n',
                               meta='<project name="home:michals:kernel-test">\n  <title>Kernel builds for branch SL-16.0</title>\n  <description />\n  <build>\n    <enable />\n  </build>\n  <publish>\n    <enable />\n    <disable repository="QA" />\n  </publish>\n  <debuginfo>\n    <enable />\n  </debuginfo>\n  <repository block="local" name="standard" rebuild="local">\n    <path project="SUSE:SLFO:1.2" repository="standard" />\n    <arch>aarch64</arch>\n    <arch>ppc64le</arch>\n    <arch>s390x</arch>\n    <arch>x86_64</arch>\n  </repository>\n  <repository name="QA">\n    <path project="home:michals:kernel-test" repository="standard" />\n    <arch>aarch64</arch>\n    <arch>ppc64le</arch>\n    <arch>s390x</arch>\n    <arch>x86_64</arch>\n  </repository>\n</project>')
            self.assertTrue(st.data_consumed)
        self.log_cycle(test_fn, 'tests/api/obsapi_create_project')

class FakeRequest:
    def __init__(self, content):
        self.content = content

class FakeOBS:
    def __init__(self, prjmeta):
        self.prjmeta = prjmeta

    def project_exists(self, project):
        prj = self.prjmeta.get(project, None)
        return FakeRequest(prj) if prj else None

    def group_exists(self, group):
        return group in self.groups

    def user_exists(self, user):
        return user in self.users

class TestUploader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open('tests/api/test_repos.yaml', 'r') as fd:
                    cls.testdata = yaml.safe_load(fd)

    def test_repo_archs(self):
        for project in ['Devel:Kernel:SLE15-SP6', 'Kernel:SLE15-SP6', 'Devel:Kernel:master', 'Kernel:HEAD']:
            prjmeta = self.testdata[project]['in']
            ul = UploaderBase()
            ul.obs = FakeOBS(prjmeta)
            ul.project = project
            if 'SP6' in project:
                ul.data = 'tests/kutil/rpm/krn'
            else:
                ul.data = 'tests/kutil/rpm/krnf'
            if project.startswith('Devel'):
                ul.obs.url = 'https://api.suse.de'
            else:
                ul.obs.url = 'https://api.opensuse.org'
            self.assertEqual(ul.get_project_repo_archs(), self.testdata[project]['out'])

    def test_prjmeta_factory(self):
        ul = UploaderBase()
        project = 'Devel:Kernel:master'
        ul.obs = FakeOBS(self.testdata[project]['in'])
        ul.project = project
        ul.data = 'tests/kutil/rpm/krnf'
        ul.obs.url = 'https://api.suse.de'
        reference = '''
<project name="Devel:Kernel:master">
  <title>Kernel builds for branch master</title>
  <description/>
  <build>
    <enable/>
  </build>
  <publish>
    <enable/>
    <disable repository="QA"/>
    <disable repository="QA_ARM"/>
    <disable repository="QA_LEGACYX86"/>
    <disable repository="QA_PPC"/>
    <disable repository="QA_RISCV"/>
    <disable repository="QA_S390"/>
  </publish>
  <debuginfo>
    <disable/>
  </debuginfo>
  <repository name="standard" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Factory" repository="standard"/>
    <arch>x86_64</arch>
  </repository>
  <repository name="S390" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Factory:zSystems" repository="standard"/>
    <arch>s390x</arch>
  </repository>
  <repository name="RISCV" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Factory:RISCV" repository="standard"/>
    <arch>riscv64</arch>
  </repository>
  <repository name="QA_S390">
    <path project="Devel:Kernel:master" repository="S390"/>
    <arch>s390x</arch>
  </repository>
  <repository name="QA_RISCV">
    <path project="Devel:Kernel:master" repository="RISCV"/>
    <arch>riscv64</arch>
  </repository>
  <repository name="QA_PPC">
    <path project="Devel:Kernel:master" repository="PPC"/>
    <arch>ppc64le</arch>
  </repository>
  <repository name="QA_LEGACYX86">
    <path project="Devel:Kernel:master" repository="LEGACYX86"/>
    <arch>i586</arch>
  </repository>
  <repository name="QA_ARM">
    <path project="Devel:Kernel:master" repository="ARM"/>
    <arch>aarch64</arch>
    <arch>armv7l</arch>
    <arch>armv6l</arch>
  </repository>
  <repository name="QA">
    <path project="Devel:Kernel:master" repository="standard"/>
    <arch>x86_64</arch>
  </repository>
  <repository name="PPC" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Factory:PowerPC" repository="standard"/>
    <arch>ppc64le</arch>
  </repository>
  <repository name="LEGACYX86" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Factory:LegacyX86" repository="standard"/>
    <arch>i586</arch>
  </repository>
  <repository name="ARM" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Factory:ARM" repository="standard"/>
    <arch>aarch64</arch>
    <arch>armv7l</arch>
    <arch>armv6l</arch>
  </repository>
</project>
'''
        self.xmldiff(reference, ul.prjmeta())

    def test_prjmeta_factory_limit(self):
        ul = UploaderBase()
        project = 'Devel:Kernel:master'
        ul.obs = FakeOBS(self.testdata[project]['in'])
        ul.project = project
        ul.data = 'tests/kutil/rpm/krnf'
        ul.obs.url = 'https://api.suse.de'
        reference = '''
<project name="Devel:Kernel:master">
  <title>Kernel builds for branch master</title>
  <description/>
  <build>
    <enable/>
  </build>
  <publish>
    <enable/>
    <disable repository="QA_ARM"/>
    <disable repository="QA_S390"/>
  </publish>
  <debuginfo>
    <disable/>
  </debuginfo>
  <repository name="S390" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Factory:zSystems" repository="standard"/>
    <arch>s390x</arch>
  </repository>
  <repository name="QA_S390">
    <path project="Devel:Kernel:master" repository="S390"/>
    <arch>s390x</arch>
  </repository>
  <repository name="QA_ARM">
    <path project="Devel:Kernel:master" repository="ARM"/>
    <arch>armv6l</arch>
  </repository>
  <repository name="ARM" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Factory:ARM" repository="standard"/>
    <arch>armv6l</arch>
  </repository>
</project>
'''
        self.xmldiff(reference, ul.prjmeta(limit_packages=['kernel-zfcpdump','dtb-armv6l']))

    def test_prjmeta_sle(self):
        ul = UploaderBase()
        project = 'Devel:Kernel:SLE15-SP6'
        ul.obs = FakeOBS(self.testdata[project]['in'])
        ul.project = project
        ul.obs.users = ['jones_tony', 'kernelbugs', 'michals', 'osalvador', 'sthackarajan', 'tiwai']
        ul.obs.groups = ['kernel-maintainers']
        ul.data = 'tests/kutil/rpm/krn'
        ul.obs.url = 'https://api.suse.de'
        reference = '''
<project name="Devel:Kernel:SLE15-SP6">
  <title>Kernel builds for branch unknown</title>
  <description/>
  <group groupid="kernel-maintainers" role="maintainer"/>
  <person userid="jones_tony" role="maintainer"/>
  <person userid="kernelbugs" role="maintainer"/>
  <person userid="michals" role="maintainer"/>
  <person userid="osalvador" role="maintainer"/>
  <person userid="sthackarajan" role="maintainer"/>
  <person userid="tiwai" role="maintainer"/>
  <build>
    <enable/>
  </build>
  <publish>
    <enable/>
    <disable repository="QA"/>
    <disable repository="QA_ARM"/>
  </publish>
  <debuginfo>
    <enable/>
  </debuginfo>
  <repository name="standard" rebuild="local" block="local">
    <path project="SUSE:SLE-15-SP6:Update" repository="standard"/>
    <arch>x86_64</arch>
    <arch>s390x</arch>
    <arch>ppc64le</arch>
    <arch>aarch64</arch>
  </repository>
  <repository name="QA_ARM">
    <path project="Devel:Kernel:SLE15-SP6" repository="ARM"/>
    <arch>armv7l</arch>
  </repository>
  <repository name="QA">
    <path project="Devel:Kernel:SLE15-SP6" repository="standard"/>
    <arch>x86_64</arch>
    <arch>s390x</arch>
    <arch>ppc64le</arch>
    <arch>aarch64</arch>
  </repository>
  <repository name="ARM" rebuild="local" block="local">
    <path project="openSUSE.org:openSUSE:Step:15-SP6" repository="standard"/>
    <arch>armv7l</arch>
  </repository>
</project>
'''
        self.xmldiff(reference, ul.prjmeta(debuginfo=True, maintainers=ul.obs.groups + ul.obs.users + ['vzzchlt']))

        reference = '''
<project name="Devel:Kernel:SLE15-SP6">
  <title>Kernel builds for branch unknown</title>
  <description/>
  <group groupid="kernel-maintainers" role="maintainer"/>
  <person userid="jones_tony" role="maintainer"/>
  <person userid="kernelbugs" role="maintainer"/>
  <person userid="michals" role="maintainer"/>
  <person userid="osalvador" role="maintainer"/>
  <person userid="sthackarajan" role="maintainer"/>
  <person userid="tiwai" role="maintainer"/>
  <build>
    <enable/>
  </build>
  <publish>
    <enable/>
    <disable repository="QA"/>
    <disable repository="QA_ARM"/>
  </publish>
  <debuginfo>
    <disable/>
  </debuginfo>
  <repository name="standard">
    <path project="SUSE:SLE-15-SP6:Update" repository="standard"/>
    <arch>x86_64</arch>
    <arch>s390x</arch>
    <arch>ppc64le</arch>
    <arch>aarch64</arch>
  </repository>
  <repository name="QA_ARM">
    <path project="Devel:Kernel:SLE15-SP6" repository="ARM"/>
    <arch>armv7l</arch>
  </repository>
  <repository name="QA">
    <path project="Devel:Kernel:SLE15-SP6" repository="standard"/>
    <arch>x86_64</arch>
    <arch>s390x</arch>
    <arch>ppc64le</arch>
    <arch>aarch64</arch>
  </repository>
  <repository name="ARM">
    <path project="openSUSE.org:openSUSE:Step:15-SP6" repository="standard"/>
    <arch>armv7l</arch>
  </repository>
</project>
'''
        self.xmldiff(reference, ul.prjmeta(rebuild=True, maintainers=ul.obs.groups + ul.obs.users))


    def xmldiff(self, reference, result):
        reference = ET.tostring(ET.fromstring(reference), encoding='unicode')  # OBS uses <tag/> but ET uses <tag />
        self.printdiff(reference, result)

    def printdiff(self, reference, result):
        self.maxDiff = None
        print('\n'.join(unified_diff(reference.splitlines(), result.splitlines(), fromfile='reference', tofile='result')))
        # Output is not stable on python 3.4, probably a bug
        # The difference is irrelevant for prjmeta but makes test output unreproducible
        if sys.version_info.major == 3 and sys.version_info.minor < 6:
            self.assertEqual(len(reference), len(result))
        else:
            self.assertEqual(reference.splitlines(), result.splitlines())

    def test_prjconf_factory(self):
        ul = UploaderBase()
        project = 'Devel:Kernel:master'
        ul.obs = FakeOBS(self.testdata[project]['in'])
        ul.project = project
        ul.ignore_kabi_badness = True
        ul.data = 'tests/kutil/rpm/krnf'
        ul.obs.url = 'https://api.suse.de'
        reference = '''Substitute: kernel-dummy
Substitute: rpmlint-Factory
Substitute: post-build-checks-malwarescan
Macros:
%is_kotd 1
%ignore_kabi_badness 1
%klp_ipa_clones 1
%is_kotd_qa (0||("%_repository" == "QA")||("%_repository" == "QA_ARM")||("%_repository" == "QA_LEGACYX86")||("%_repository" == "QA_PPC")||("%_repository" == "QA_RISCV")||("%_repository" == "QA_S390"))
:Macros
BuildFlags: excludebuild:kernel-source:kernel-obs-qa
BuildFlags: excludebuild:kernel-obs-qa
BuildFlags: nouseforbuild:kernel-source:kernel-obs-build
BuildFlags: nouseforbuild:kernel-obs-build
%if 0||("%_repository" == "QA")||("%_repository" == "QA_ARM")||("%_repository" == "QA_LEGACYX86")||("%_repository" == "QA_PPC")||("%_repository" == "QA_RISCV")||("%_repository" == "QA_S390")
BuildFlags: !excludebuild:kernel-source:kernel-obs-qa
BuildFlags: !excludebuild:kernel-obs-qa
BuildFlags: onlybuild:kernel-source:kernel-obs-qa
BuildFlags: onlybuild:kernel-obs-qa
BuildFlags: onlybuild:kernel-obs-build.agg
BuildFlags: onlybuild:nonexistent-package
BuildFlags: !nouseforbuild:kernel-source:kernel-obs-build
BuildFlags: !nouseforbuild:kernel-obs-build
%endif
'''
        self.printdiff(reference, ul.prjconf(debuginfo=True))

    def test_prjconf_factory_limit(self):
        ul = UploaderBase()
        project = 'Devel:Kernel:master'
        ul.obs = FakeOBS(self.testdata[project]['in'])
        ul.project = project
        ul.ignore_kabi_badness = True
        ul.data = 'tests/kutil/rpm/krnf'
        ul.obs.url = 'https://api.suse.de'
        reference = '''Substitute: kernel-dummy
Substitute: rpmlint-Factory
Substitute: post-build-checks-malwarescan
Macros:
%is_kotd 1
%ignore_kabi_badness 1
%klp_ipa_clones 1
%is_kotd_qa (0||("%_repository" == "QA_ARM")||("%_repository" == "QA_S390"))
:Macros
BuildFlags: onlybuild:kernel-zfcpdump
BuildFlags: onlybuild:dtb-armv6l
'''
        self.printdiff(reference, ul.prjconf(debuginfo=True, limit_packages=['kernel-zfcpdump', 'dtb-armv6l']))

    def test_prjconf_klp(self):
        ul = UploaderBase()
        project = 'Devel:kGraft:patches:SLE15-SP7-RT_Update_0'
        ul.obs = FakeOBS(self.testdata[project]['in'])
        ul.project = project
        ul.ignore_kabi_badness = False
        ul.data = 'tests/kutil/rpm/klp'
        ul.obs.url = 'https://api.suse.de'
        reference = '''%ifarch %ix86 x86_64
Constraint: hardware:processors 8
%endif
%ifarch %ix86 x86_64 ia64 ppc ppc64 ppc64le
Constraint: hardware:disk:size unit=G 14
%else
Constraint: hardware:disk:size unit=G 7
%endif
Substitute: kernel-dummy
Macros:
%is_kotd 1
%klp_ipa_clones 1
%is_kotd_qa (0||("%_repository" == "QA"))
:Macros
BuildFlags: excludebuild:kernel-livepatch-SLE15-SP7-RT_Update_0:kernel-obs-qa
BuildFlags: excludebuild:kernel-obs-qa
BuildFlags: nouseforbuild:kernel-livepatch-SLE15-SP7-RT_Update_0:kernel-obs-build
BuildFlags: nouseforbuild:kernel-obs-build
%if 0||("%_repository" == "QA")
BuildFlags: !excludebuild:kernel-livepatch-SLE15-SP7-RT_Update_0:kernel-obs-qa
BuildFlags: !excludebuild:kernel-obs-qa
BuildFlags: onlybuild:kernel-livepatch-SLE15-SP7-RT_Update_0:kernel-obs-qa
BuildFlags: onlybuild:kernel-obs-qa
BuildFlags: onlybuild:kernel-obs-build.agg
BuildFlags: onlybuild:nonexistent-package
BuildFlags: !nouseforbuild:kernel-livepatch-SLE15-SP7-RT_Update_0:kernel-obs-build
BuildFlags: !nouseforbuild:kernel-obs-build
%endif
'''
        self.printdiff(reference, ul.prjconf(debuginfo=True, rpm_checks=True))
