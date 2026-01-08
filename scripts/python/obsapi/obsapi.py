import xml.etree.ElementTree as ET
from obsapi.api import APIError
from obsapi import api
import http.cookiejar
import configparser
import urllib.parse
import collections
import subprocess
import tempfile
import base64
import time
import bz2
import sys
import re
import os

if not hasattr(ET, 'indent'):  # should be available since python 3.9
    import ETindent
    ET.indent = ETindent.indent

PkgRepo = collections.namedtuple('PkgRepo', ['api', 'org', 'repo', 'branch', 'commit'])

def expand_home(path):
    if path.startswith('~/'):
        path = os.environ['HOME'] + path[1:]
    return path

class OBSAPI(api.API):
    def __init__(self, URL, logfile=None, config=None, cookiejar=None, ca=None):
        self.config = config
        URL = URL.rstrip('/')
        self.url = URL
        self.get_token(cookiejar)
        super().__init__(URL, logfile, ca)

    def get_token(self, cookiejar):
        if self.config == None:
            configs = [os.environ['HOME'] + '/.oscrc', os.environ['HOME'] + '/.config/osc/oscrc']
            for config in configs:
                if os.path.exists(config):
                    self.config = config
                    break
            if not self.config:
                raise RuntimeError('Could not find an osc configuration file in ' + ' '.join(configs))
        if not cookiejar:
            cookiejar = os.environ['HOME'] + '/.local/state/osc/cookiejar'
        self.cookiejar = http.cookiejar.LWPCookieJar(cookiejar)
        try:
            self.cookiejar.load()
        except FileNotFoundError:
            None
        except Exception as e:
            sys.stderr.write("Error loading cookies: %s\n" % (repr(e),))
        cp = configparser.ConfigParser(delimiters=('=', ':'), interpolation=None)
        try:
            cp.read(self.config)
        except (FileNotFoundError, PermissionError) as e:
            sys.stderr.write('Error loading osc configuration file ' + self.config + ' : ' + str(e) + '\n')
        if self.url not in cp:
            raise RuntimeError('No configuration for API ' + self.url + ' in ' + self.config)
        config = cp[self.url]
        self.user = config.get('user', None)
        if not self.user:
            raise RuntimeError('No username found in ' + self.url + ' configuration.')
        self.sshkey = None
        if 'sshkey' in config:
            self.sshkey = config['sshkey']
            self.sshkey = expand_home(self.sshkey)
            self.sshkey = os.path.join(expand_home('~/.ssh'), self.sshkey)  # python curious path join semantic
            if not os.path.exists(self.sshkey):
                raise RuntimeError('Key file does not exist ' + self.sshkey)
            return
        passx = None
        if 'passx' in config:
            passx = config['passx']
        elif 'pass' in config and config.get('credentials_mgr_class', None) == 'osc.credentials.ObfuscatedConfigFileCredentialsManager':
            passx = config['pass']
        if passx:
            passw = bz2.decompress(base64.standard_b64decode(passx)).decode()
        else:
            passw = config.get('pass', None)
        if not passw:
            cmc = config.get('credentials_mgr_class', None)
            if 'keyring' in config or 'gnome_keyring' in config or cmc == 'osc.credentials.KeyringCredentialsManager:keyring.backends.SecretService.Keyring':
                assert self.url.startswith('https://')
                host = self.url[       len('https://'):]
                passw = subprocess.check_output('secret-tool', 'lookup', 'service', host, 'username', self.user)
                assert len(passw) > 0
            else:
                raise RuntimeError('No password found in ' + self.url + ' configuration. Authentication type ' + str(cmc) + ' not supported.')
        self.passw = passw

    def ssh_signature(self, created, user, sshkey, realm):
        with tempfile.TemporaryDirectory() as td:
            fn = os.path.join(td, 'data')
            with open(fn, 'w') as f:
                f.write('(created): ' + str(created))
            subprocess.check_call(['ssh-keygen', '-Y', 'sign', '-f', sshkey, '-n', realm, '-q', fn])
            with open(fn + '.sig', 'r') as f:
                sig = f.read().splitlines()
            if sig[0] != '-----BEGIN SSH SIGNATURE-----' or sig[-1] != '-----END SSH SIGNATURE-----':
                raise RuntimeError('Failed to create a SSH signature')
        sig = ''.join(sig[1:-1])
        sig = base64.standard_b64encode(base64.b64decode(sig.encode(), validate=True)).decode()
        sig = 'keyId="%s",algorithm="ssh",headers="(created)",created=%i,signature="%s"' % (user, created, sig)
        return sig

    def auth_header(self, wwwa):
        if self.sshkey:
            wwwa = wwwa.get('Signature', {})
            if 'realm' not in wwwa:
                raise RuntimeError('No realm received for SSH authentication')
            sig = self.ssh_signature(int(time.time()), self.user, self.sshkey, wwwa['realm'])
            return {'Authorization' : 'Signature ' + sig }
        return {'Authorization' : 'Basic ' + base64.standard_b64encode((self.user + ':' + self.passw).encode()).decode()}

    def check_login(self):
        # This redirects creating 3 requests when not authenticated,
        # checking the relevant combinations of cookies and authentication
        r = self.get('/')
        return r

    def group_exists(self, group):
        return self.check_exists('/'.join(['/group', group]))

    def user_exists(self, user):
        return self.check_exists('/'.join(['/person', user]))

    def project_exists(self, project):
        return self.check_exists('/'.join(['/source', project, '_meta']))

    def create_project(self, project, meta, conf):
        self.check_put('/'.join(['/source', project, '_meta?force=1']), headers={'Content-type': 'application/xml'}, data=meta)
        # OBS insists on content type for this file
        self.check_put('/'.join(['/source', project, '_config']), headers={'Content-type': 'text/plain'}, data=conf)

    def delete_project(self, project):
        return self.check_delete('/'.join(['/source', project] + '?force=1'))

    def package_exists(self, project, package):
        return self.file_exists(project, package, '_meta')

    def create_package_meta(self, project, package, meta):
        return self.upload_file(project, package, '_meta', meta, 'application/xml')

    def create_package(self, project, package):
        pkgmeta = ET.Element('package', name=package, project=project)
        title = ET.SubElement(pkgmeta, 'title')
        title.text = package
        ET.SubElement(pkgmeta, 'description')
        ET.indent(pkgmeta)
        return self.create_package_meta(project, package, ET.tostring(pkgmeta))

    def delete_package(self, project, package):
        self.check_delete('/'.join(['/source', project, package]))

    def create_link(self, project, link, package):
        linkxml = ET.Element('link', package=package, cicount='copy')
        self.create_package(project, link)
        self.upload_file(project, link, '_link', ET.tostring(linkxml), 'application/xml')

    def file_exists(self, project, package, file):
        return self.check_exists('/'.join(['/source', project, package, file]))

    def package_meta(self, project, package):
        return ET.fromstring(self.check_get('/'.join(['/source', project, package, '_meta'])).content)

    def upload_file(self, project, package, file, data, content_type='application/octet-stream'):
        return self.check_put('/'.join(['/source', project, package, file]), headers={'Content-type': content_type}, data=data)

    def package_scmsync(self, project, package):
        return urllib.parse.urlparse(self.package_meta(project, package).find('scmsync').text)

    def package_repo(self, project, package):
        if self.package_exists(project, package) and self.package_meta(project, package).find('scmsync') != None:
            sync = self.package_scmsync(project, package)
            assert sync.scheme == 'https'
            assert sync.netloc in ['src.suse.de', 'src.opensuse.org']
            assert len(sync.fragment) == 64 or len(sync.fragment) == 40
            assert re.fullmatch('(?ai)[a-f0-9]*',sync.fragment)
            query = urllib.parse.parse_qs(sync.query)
            assert list(query.keys()) == ['trackingbranch'] or list(query.keys()) == []
            branch = query['trackingbranch'][0] if 'trackingbranch' in query else None
            assert len(sync.path.split('/')) == 3
            _, org, repo = sync.path.split('/')
            assert _ == ''
            return PkgRepo(sync.scheme + '://' + sync.netloc, org, repo, branch, sync.fragment)
        if self.url == 'https://api.suse.de':
            api = 'https://src.suse.de'
        elif self.url == 'https://api.opensuse.org':
            api = 'https://src.opensuse.org'
        elif self.url.startswith('https://127.0.0.1:'):
            api = self.url  # test environment
        else:
            raise APIError('No default Gitea API for %s' % (self.url,))
        return PkgRepo(api, 'pool', package, None, None)

    def list_projects(self):
        xml = ET.fromstring(self.check_get('/source').content)
        assert xml.tag == 'directory'
        assert len(xml.keys()) == 0
        result = []
        for e in xml.iter('entry'):
            assert len(e.keys()) == 1
            result.append(e.get('name'))
        assert len(xml) == len(result)
        return result

    def list_project_packages(self, project):
        xml = ET.fromstring(self.check_get('/source/' + project).content)
        assert xml.tag == 'directory'
        assert len(xml.keys()) == 1
        result = []
        for e in xml.iter('entry'):
            assert len(e.keys()) == 1
            result.append(e.get('name'))
        assert (len(xml) == len(result)) and (len(result) == int(xml.get('count')))
        return result

    def list_package_links(self, project, package):
        xml = ET.fromstring(self.check_post('/source/' + project + '/' + package, params={'cmd': 'showlinked'}).content)
        assert xml.tag == 'collection'
        assert len(xml.keys()) == 0
        result = []
        remote = 0
        for e in xml.iter('package'):
            assert len(e.keys()) == 2
            if e.get('project') == project:
                result.append(e.get('name'))
            else:
                remote += 1
        assert len(xml) == len(result) + remote
        return result
