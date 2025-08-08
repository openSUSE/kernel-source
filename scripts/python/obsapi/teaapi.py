from collections import namedtuple
from obsapi.api import APIError
from obsapi import api
import subprocess
import tempfile
import hashlib
import base64
import json
import yaml
import sys
import os

File = namedtuple('File',['oid', 'size', 'name', 'lfs', 'lfs_oid', 'lfs_size'])

def ref_arg(ref):
    return { 'ref' : ref }

class TeaAPI(api.API):
    def __init__(self, URL, logfile=None, config=None):
        self.config = config
        URL = URL.rstrip('/')
        super().__init__(URL, logfile)
        self.get_token()

    def get_token(self):
        if self.config == None:
            self.config = os.environ['HOME'] + '/.config/tea/config.yml'
        try:
            with open(self.config, 'r') as file:
                config = yaml.safe_load(file)
        except (FileNotFoundError, PermissionError, yaml.YAMLError) as e:
            sys.stderr.write('Error loading gitea-tea configuration file ' + self.config + ' : ' + str(e) + '\n')
            config = { 'logins': [] }

        try:
            self.token = [login['token'] for login in config['logins'] if login['url'] == self.url][0]
        except IndexError:
            sys.stderr.write('Cannot find gitea-tea configuration for ' + self.url + '\nPlease configure tea with a token that has readwrite access to user and repository with\ntea login add')
            exit(1)

    def auth_header(self):
        return {'Authorization' : 'token ' + self.token}

    def auth_header_json(self):
        hdr = self.auth_header()
        hdr['Content-type'] = 'application/json'
        return hdr

    def repo_path(self, org, repo):
        return '/api/v1/repos/' + org + '/' + repo

    def update_gitattr(self, org, repo, branch):
        fn = '.gitattributes'
        r = self.check_exists(self.repo_path(org, repo) + '/contents/' + fn, headers=self.auth_header(), params=ref_arg(branch))
        attributes = [
                '*.tar.bz2 filter=lfs diff=lfs merge=lfs -text',
                '*.tar.?z filter=lfs diff=lfs merge=lfs -text',
                ]
        sha = None
        if r:
            fileinfo = r.json()
            sha = fileinfo['sha']
            content = base64.standard_b64decode(fileinfo['content']).decode().splitlines()
        else:
            content = []
        for a in attributes:
            if a not in content:
                content.append(a)
        content = '\n'.join(content) + '\n'
        content = base64.standard_b64encode(content.encode()).decode()
        if not sha or (content != fileinfo['content']):
            data = {
                'branch' : branch,
                'content': content,
                }
            method = 'POST'
            if sha:
                data['sha'] = sha
                method = 'PUT'
            self.check(method, self.repo_path(org, repo) + '/contents/' + fn, headers=self.auth_header_json(), json=data)
