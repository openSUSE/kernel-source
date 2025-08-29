from collections import namedtuple
from obsapi import api
import subprocess
import tempfile
import hashlib
import base64
import json
import yaml
import sys
import os

def ref_arg(ref):
    return { 'ref' : ref }

class TeaAPI(api.API):
    def __init__(self, URL, logfile=None, config=None, ca=None):
        self.config = config
        URL = URL.rstrip('/')
        super().__init__(URL, logfile, ca)
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

    def auth_header(self, wwwa):
        return {'Authorization' : 'token ' + self.token}

    def get_user(self):
        r = self.check_get('/api/v1/user')
        user = r.json()['login']
        return user

    def repo_path(self, org, repo):
        return '/api/v1/repos/' + org + '/' + repo

    def repo_branches(self, org, repo):
        r = self.check_get(self.repo_path(org, repo) + '/branches', params={
            'limit' : 1000,
            })
        branch_count = int(r.headers['X-Total-Count'])
        branches = r.json()
        if branches:
            dic = {}
            for b in branches:
                dic[b['name']] = b
            branches = dic
        else:
            branches = {}
        if branch_count != len(branches.keys()):
            sys.stderr.write('%s/%s: Number of branches retrieved %i is not equal branch count %i' % (org, repo, branch_count, len(branches)))
        return branches

    def delete_branch(self, org, repo, branch):
        return self.check_delete(self.repo_path(org, repo) + '/branches/' + branch)

    def repo_commit(self, org, repo, commit):
        return self.check_get(self.repo_path(org, repo) + '/git/commits/' + commit, params = {
            'stat' : False,
            'files' : False,
            'verification' : False,
            })

    def create_branch(self, org, repo, branch, ref_branch, commit, reset=False):
        branches = self.repo_branches(org, repo)
        if commit:
            assert self.repo_commit(org, repo, commit)
        elif ref_branch:
            assert ref_branch in branches
        if branch in branches:
            if not reset:
                return
            if not commit and not ref_branch:
                raise api.APIError("Branch reset requested but no reference is provided.")
            current_commit = branches[branch]['commit']['id']
            if commit:
                if current_commit != commit:
                    sys.stderr.write('Deleting branch %s (commit mismatch %s %s)\n' %
                                     (branch, current_commit, commit))
                else:
                    return
            elif ref_branch:
                ref_commit = branches[ref_branch]['commit']['id']
                if current_commit != ref_commit:
                    sys.stderr.write('Deleting branch %s (commit mismatch %s %s)\n' %
                                     (branch, current_commit, ref_commit))
                else:
                    return
            self.delete_branch(org, repo, branch)  # no branch update feature
        ref = None
        if commit:
            ref = commit
        elif ref_branch:
            ref = ref_branch
        json = { 'new_branch_name' : branch }
        if ref:
            json['old_ref_name'] = ref
        return self.check_post(self.repo_path(org, repo) + '/branches', json=json)

    def update_gitattr(self, org, repo, branch):
        fn = '.gitattributes'
        r = self.check_exists(self.repo_path(org, repo) + '/contents/' + fn, params=ref_arg(branch))
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
            self.check(method, self.repo_path(org, repo) + '/contents/' + fn, json=data)
