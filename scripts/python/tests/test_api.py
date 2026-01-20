from kutil.config import get_package_archs, get_kernel_projects
from obsapi.teaapi import TeaAPI, json_custom_dump
from obsapi.obsapi import OBSAPI, PkgRepo
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
import shutil
import types
import json
import yaml
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
  "H": [  ]
}
'''
],
                [ {}, '''{
}
'''
                 ],
                ]
        for data, result in testdata:
            self.assertEqual(json_custom_dump(data), result)


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
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.update_gitattr('michals', 'testrepo', 'testbranch')
        self.assertTrue(st.data_consumed)

    def test_file_up_to_date(self):
        st = ServerThread('tests/api/gitattr_up_to_date')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.update_file('michals', 'testrepo', 'testbranch', '.gitattributes', '''*.tar.?z filter=lfs diff=lfs merge=lfs -text
foobar
*.tar.bz2 filter=lfs diff=lfs merge=lfs -text
''')
        self.assertTrue(st.data_consumed)

    def test_gitattr_nonexistent_file(self):
        st = ServerThread('tests/api/gitattr_nonexistent_file')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.update_gitattr('michals', 'testrepo', 'testbranch')
        self.assertTrue(st.data_consumed)

    def test_file_nonexistent(self):
        st = ServerThread('tests/api/gitattr_nonexistent_file')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.update_file('michals', 'testrepo', 'testbranch', '.gitattributes', '''*.tar.bz2 filter=lfs diff=lfs merge=lfs -text
*.tar.?z filter=lfs diff=lfs merge=lfs -text
''')
        self.assertTrue(st.data_consumed)

    def test_gitattr_needs_update(self):
        st = ServerThread('tests/api/gitattr_needs_update')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.update_gitattr('michals', 'testrepo', 'testbranch')
        self.assertTrue(st.data_consumed)

    def test_file_needs_update(self):
        st = ServerThread('tests/api/gitattr_needs_update')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.update_file('michals', 'testrepo', 'testbranch', '.gitattributes', '''*.tar.?z filter=lfs diff=lfs merge=lfs -text
foobar
*.tar.bz2 filter=lfs diff=lfs merge=lfs -text
''')
        self.assertTrue(st.data_consumed)

    def test_file_needs_update_incomplete(self):
        st = ServerThread('tests/api/gitattr_needs_update')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.update_file('michals', 'testrepo', 'testbranch', '.gitattributes', '''*.tar.?z filter=lfs diff=lfs merge=lfs -text
foobar''')
        self.assertFalse(st.data_consumed)

    def test_gitattr_nonexistent_repo(self):
        st = ServerThread('tests/api/gitattr_nonexistent_repo')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        with self.assertRaisesRegex(APIError, '/api/v1/repos/michals/testrepo/contents/.gitattributes POST 404 Not Found'):
            api.update_gitattr('michals', 'testrepo', 'testbranch')
        self.assertTrue(st.data_consumed)

    def test_content_update(self):
        st = ServerThread('tests/api/update_content')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.update_content('michals', 'testrepo', 'testbranch', 'tests/api/content/update', 'Update flies')
        self.assertTrue(st.data_consumed)

    def test_create_branch(self):
        st = ServerThread('tests/api/branch_new')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.create_branch('michals', 'testrepo', 'downstream', 'testbranch', '60298bc4bf915a41f8f16f64d05a4125b434ca63112c53ba6779b039123c6db6', True)
        self.assertTrue(st.data_consumed)
        st = ServerThread('tests/api/branch_up_to_date')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.create_branch('michals', 'testrepo', 'downstream', 'testbranch', '60298bc4bf915a41f8f16f64d05a4125b434ca63112c53ba6779b039123c6db6', True)
        self.assertTrue(st.data_consumed)
        st = ServerThread('tests/api/branch_no_roll')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.create_branch('michals', 'testrepo', 'downstream', 'testbranch', 'a0156cd1f6cc836cec02b406a8c5154311bcd800e431a4092e5b59f611049ee4', False)
        self.assertTrue(st.data_consumed)
        st = ServerThread('tests/api/branch_roll_forward')
        st.start_server(teaconfig=self.config)
        api = TeaAPI(st.url(), config=self.config, ca=st.servercert)
        api.create_branch('michals', 'testrepo', 'downstream', 'testbranch', 'a0156cd1f6cc836cec02b406a8c5154311bcd800e431a4092e5b59f611049ee4', True)
        self.assertTrue(st.data_consumed)

class TestOBS(unittest.TestCase):
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

    def test_basic(self):
        st = ServerThread('tests/api/obsapi_basic')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        api.check_login()
        self.assertTrue(st.data_consumed)

    def test_SSL(self):
        st = ServerThread('tests/api/obsapi_basic')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar)
        with self.assertRaisesRegex(Exception, 'certificate verify failed'):
            api.check_login()
        self.assertFalse(st.data_consumed)

    def test_Y(self):
        st = ServerThread('tests/api/obsapi_log_in')
        st.start_server(obsconfig=self.config)
        os.unlink(self.cookiejar)
        config = configparser.ConfigParser(delimiters=('='), interpolation=None)
        config.read(self.config)
        # permissions not stored exactly in git, ssh refuses to read 666 files
        try:
            os.chmod('tests/api/testkey', 0o400)
        except OSError:  # readonly filesystem in container
            None
        config[config.sections()[0]]['sshkey'] = os.path.abspath('tests/api/testkey')
        with open(self.config, 'w') as f:
            config.write(f)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        self.assertEqual(api.ssh_signature(1755779838, api.user, api.sshkey, 'some realm'),
                         'keyId="obsuser",algorithm="ssh",headers="(created)",created=1755779838,signature="U1NIU0lHAAAAAQAAADMAAAALc3NoLWVkMjU1MTkAAAAge7Wj9uPdUE8nqD2mPJ8R9tZLZ2Wgwqj1MT7sJlFhJj4AAAAKc29tZSByZWFsbQAAAAAAAAAGc2hhNTEyAAAAUwAAAAtzc2gtZWQyNTUxOQAAAEBNMTVv/cHwZMLNZ2UaNaVUX2fJw8J4LvTCcHTrpXQ2z2pr5ldM+UvKypyBExf42plNYEI3hw59V4Uzej/di5YA"')
        api.check_login()
        self.assertTrue(st.data_consumed)

    def test_pkgrepo(self):
        st = ServerThread('tests/api/obsapi_pkgrepo')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        self.assertEqual(api.package_repo('SUSE:SLFO:1.2', 'kernel-source-azure'),
                         PkgRepo(api='https://src.suse.de', org='pool', repo='kernel-source-azure', branch='slfo-1.2',
                                 commit='b20dbdf296c74a2897e61205e5c9edcb7f85340ede6bbfd18c05dbfce87c267b'))
        self.assertTrue(st.data_consumed)

    def test_pkgrepo_defalt(self):
        st = ServerThread('tests/api/obsapi_pkgrepo_no_scmsync')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        self.assertEqual(api.package_repo('SUSE:SLE-15-SP7:GA', 'kernel-source-azure'),
                         PkgRepo(api=st.url(), org='pool', repo='kernel-source-azure', branch=None, commit=None))
        self.assertTrue(st.data_consumed)

        st = ServerThread('tests/api/obsapi_pkgrepo_nonexistent_pkg')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        self.assertEqual(api.package_repo('SUSE:SLFO:1.2', 'kernel-source-foobar'),
                         PkgRepo(api=st.url(), org='pool', repo='kernel-source-foobar', branch=None, commit=None))
        self.assertTrue(st.data_consumed)

    def test_list_projects(self):
        st = ServerThread('tests/api/obsapi_list_projects')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        self.assertEqual(api.list_projects(),
                ['AlmaLinux:10', 'AlmaLinux:8', 'AlmaLinux:9', 'Alpine:Edge', 'Alpine:Latest', 'Amazon:AL2023', 'Apache', 'Apache:MirrorBrain', 'Apache:MirrorBrain:development', 'Apache:Modules', 'zypp:SLE-15-SP7-Branch', 'zypp:TEST', 'zypp:TW', 'zypp:ci', 'zypp:ci:libzypp', 'zypp:ci:zypper', 'zypp:jezypp', 'zypp:jezypp:SuSE-RES-8-Branch', 'zypp:jezypp:SuSE-RES-9-Branch', 'zypp:plugins'])
        self.assertTrue(st.data_consumed)

    def test_list_packages(self):
        st = ServerThread('tests/api/obsapi_list_packages')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        self.assertEqual(api.list_project_packages('Kernel:tools'),
                ['ShellCheck', 'bash-git-prompt', 'bison', 'boottest-ramdisk', 'boottest-ramdisk-12', 'boottest-ramdisk-15', 'boottest-ramdisk-16', 'boottest-ramdisk-16.ARM', 'boottest-ramdisk-16.PowerPC', 'capstone', 'container-base', 'cross-aarch64-gcc48', 'cross-armv7hl-gcc48', 'cross-binutils', 'cross-gcc13', 'cross-gcc14', 'cross-gcc15', 'cross-gcc48', 'cross-gcc7', 'cross-ia64-gcc48', 'cross-ppc64-gcc48', 'cross-ppc64le-gcc48', 'cross-s390x-gcc48', 'cross-x86_64-gcc48', 'dwarves.Factory', 'elfutils', 'elfutils.Factory', 'gcc13', 'gcc13.build', 'gcc14', 'gcc14.build', 'gcc15', 'gcc48', 'gcc6', 'gcc7.build', 'git', 'git-credential-oauth', 'git-fixes', 'git-lfs', 'go1.12', 'go1.14', 'go1.4', 'golang-github-cpuguy83-go-md2man', 'golang-packaging', 'grub2', 'http-parser', 'kbuild-gcc', 'kbuild-support', 'kcov', 'kernel-install-tools', 'kernel-obs-build', 'kernel-source-component', 'libcontainers-common', 'libgit2', 'libgit2.1.7', 'libgit2.1.9', 'libssh2_org', 'liburing2', 'lua-alt-getopt', 'lua-argparse', 'lua-busted', 'lua-cliargs', 'lua-compat-5.3', 'lua-dkjson', 'lua-inspect', 'lua-jsregexp', 'lua-ldoc', 'lua-loadkit', 'lua-lpeg', 'lua-lua-ev', 'lua-luacheck', 'lua-luafilesystem', 'lua-luarocks', 'lua-luassert', 'lua-luasystem', 'lua-luaterm', 'lua-macros', 'lua-markdown', 'lua-mediator_lua', 'lua-moonscript', 'lua-penlight', 'lua-say', 'lua-serpent', 'lua-shell-games', 'lua-tl', 'lua53', 'lua54', 'memory-constraints', 'obs-service-kiwi_metainfo_helper', 'patchtools', 'perl-Text-Markdown', 'pesign-obs-integration', 'python-augeas', 'python-augeas.3.11', 'python-cffi', 'python-mypy', 'python-pygit2', 'python-pygit2.3.11', 'python-typed-ast', 'python36', 'qemu', 'quickjs', 'quilt', 'rapidquilt', 'rpmdevtools', 'rust', 'skopeo', 'suse-add-cves', 'suse-get-maintainers', 'suse-kabi-tools', 'uki-tool', 'umoci', 'zstd'])
        self.assertTrue(st.data_consumed)

    def test_list_links(self):
        st = ServerThread('tests/api/obsapi_list_links')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        self.assertEqual(api.list_package_links('Kernel:SLE15-SP7', 'kernel-source'),
                ['dtb-aarch64', 'kernel-64kb', 'kernel-default', 'kernel-docs', 'kernel-kvmsmall', 'kernel-obs-build', 'kernel-obs-qa', 'kernel-syms', 'kernel-zfcpdump'])
        self.assertTrue(st.data_consumed)

    def test_create_project(self):
        st = ServerThread('tests/api/obsapi_create_project')
        st.start_server(obsconfig=self.config)
        api = OBSAPI(st.url(), config=self.config, cookiejar=self.cookiejar, ca=st.servercert)
        api.create_project('home:michals:kernel-test',
                           conf='Substitute: kernel-dummy\nSubstitute: rpmlint-Factory\nSubstitute: post-build-checks-malwarescan\nMacros:\n%is_kotd 1\n%klp_ipa_clones 1\n%is_kotd_qa (0||("%_repository" == "QA"))\n:Macros\nBuildFlags: excludebuild:kernel-source:kernel-obs-qa\nBuildFlags: excludebuild:kernel-obs-qa\nBuildFlags: nouseforbuild:kernel-source:kernel-obs-build\nBuildFlags: nouseforbuild:kernel-obs-build\n%if 0||("%_repository" == "QA")\nBuildFlags: !excludebuild:kernel-source:kernel-obs-qa\nBuildFlags: !excludebuild:kernel-obs-qa\nBuildFlags: onlybuild:kernel-source:kernel-obs-qa\nBuildFlags: onlybuild:kernel-obs-qa\nBuildFlags: onlybuild:kernel-obs-build.agg\nBuildFlags: onlybuild:nonexistent-package\nBuildFlags: !nouseforbuild:kernel-source:kernel-obs-build\nBuildFlags: !nouseforbuild:kernel-obs-build\n%endif\n',
                           meta='<project name="home:michals:kernel-test">\n  <title>Kernel builds for branch SL-16.0</title>\n  <description />\n  <build>\n    <enable />\n  </build>\n  <publish>\n    <enable />\n    <disable repository="QA" />\n  </publish>\n  <debuginfo>\n    <enable />\n  </debuginfo>\n  <repository block="local" name="standard" rebuild="local">\n    <path project="SUSE:SLFO:1.2" repository="standard" />\n    <arch>aarch64</arch>\n    <arch>ppc64le</arch>\n    <arch>s390x</arch>\n    <arch>x86_64</arch>\n  </repository>\n  <repository name="QA">\n    <path project="home:michals:kernel-test" repository="standard" />\n    <arch>aarch64</arch>\n    <arch>ppc64le</arch>\n    <arch>s390x</arch>\n    <arch>x86_64</arch>\n  </repository>\n</project>')
        self.assertTrue(st.data_consumed)

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
  <title>Kernel builds for branch SLE15-SP6</title>
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
  <title>Kernel builds for branch SLE15-SP6</title>
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
