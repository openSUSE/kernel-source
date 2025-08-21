from obsapi.api import APIError
from obsapi import api
import http.cookiejar
import configparser
import subprocess
import tempfile
import base64
import time
import bz2
import sys
import os

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
        cp = configparser.ConfigParser(delimiters=('='), interpolation=None)
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
            raise RuntimeError('No password found in ' + self.url + ' configuration. Keyring authentication not supported.')
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
