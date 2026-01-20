from kutil.config import init_repo, list_files
from obsapi import api
import subprocess
import tempfile
import hashlib
import base64
import json
import yaml
import sys
import os

class TeaAPI(api.API):
    def __init__(self, URL, logfile=None, config=None, ca=None, progress=sys.stderr):
        self.progress = progress
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
            sys.stderr.write('Cannot find gitea-tea configuration for ' + self.url + '\nPlease configure tea with a token that has readwrite access to user and repository with\ntea login add\n')
            exit(1)

    def auth_header(self, wwwa):
        return {'Authorization' : 'token ' + self.token}

    def get_user(self):
        r = self.check_get('/api/v1/user')
        user = r.json()['login']
        return user

    def log_progress(self, string):
        if self.progress:
            self.progress.write(string)

    def _page_url(self, url):
        r = self.check_get(url, params={
            'limit' : 1000,
            })
        items = r.json()
        item_count = int(r.headers['X-Total-Count'])
        page_size = len(items)
        result = items
        if page_size != item_count:
            pages = int((item_count + page_size - 1)/page_size)  # ceil
            for page in range(2, pages + 1):
                items = self.check_get(url, params={
                    'limit' : page_size,
                    'page' : page,
                    }).json()
                result += items
        assert len(result) == item_count
        return result

    def _name_dict(self, items):
        if items:
            dic = {}
            for i in items:
                dic[i['name']] = i
            return dic
        return {}

    def list_repos(self, org):
        repos = self._page_url('/api/v1/users/' + org + '/repos')
        return self._name_dict(repos)

    def repo_path(self, org, repo):
        return '/api/v1/repos/' + org + '/' + repo

    def repo_exists(self, org, repo):
        return self.check_exists(self.repo_path(org, repo))

    def fork_repo(self, src, user, repo):
        if self.repo_exists(src, repo):
            self.check_post(self.repo_path(src, repo) + '/forks', json={
                'name' : repo,
                })
        else:
            self.check_post('/api/v1/user/repos', json={
                'name' : repo,
                'object_format_name' : 'sha256',
                })
        self.check_patch(self.repo_path(user, repo), json={
            'description' : 'Automatically generated; do not edit',
            'has_actions' : False,
            'has_issues' : False,
            'has_packages' : False,
            'has_projects' : False,
            'has_pull_requests' : False,
            'has_releases' : False,
            'has_wiki' : False,
            })
        return self.repoinfo(user, repo)

    def repoinfo(self, org, repo):
        r = self.check_get(self.repo_path(org, repo))
        repoinfo = r.json()
        return repoinfo

    def repo_branches(self, org, repo):
        branches = self._page_url(self.repo_path(org, repo) + '/branches')
        return self._name_dict(branches)

    def delete_branch(self, org, repo, branch):
        return self.check_delete(self.repo_path(org, repo) + '/branches/' + branch)

    def repo_commit(self, org, repo, commit):
        return self.get(self.repo_path(org, repo) + '/git/commits/' + commit, params = {
            'stat' : False,
            'files' : False,
            'verification' : False,
            })

    def repo_commit_exists(self, org, repo, commit):
        c = self.repo_commit(org, repo, commit)
        if c.status == 404:
            sys.stderr.write('Commit %s not in %s/%s %s\n' % (commit, org, repo, c.status_message_pretty))
            return False
        c.raise_for_status()
        return c

    def merge_upstream_branch(self, org, repo, branch):
        if not branch in self.repo_branches(org, repo):
            self.create_branch(org, repo, branch, None, None)
        return self.post(self.repo_path(org, repo) + '/merge-upstream', json = {
            'branch': branch,
            })

    def create_branch(self, org, repo, branch, ref_branch, commit, reset=False):
        branches = self.repo_branches(org, repo)
        if commit and not self.repo_commit_exists(org, repo, commit):
            commit = None
        if not commit and  ref_branch:
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
        self.update_file_lines(org, repo, branch, '.gitattributes', [
                '*.tar.bz2 filter=lfs diff=lfs merge=lfs -text',
                '*.tar.?z filter=lfs diff=lfs merge=lfs -text',
                ])

    def get_file(self, org, repo, branch, fn):
        return self.check_exists(self.repo_path(org, repo) + '/contents/' + fn, params={'ref': branch})

    def get_file_data(self, org, repo, branch, fn):
        r = self.get_file(org, repo, branch, fn)
        if r:
            return base64.standard_b64decode(r.json()['content']).decode()
        return r

    def update_file_lines(self, org, repo, branch, fn, lines):
        r = self.get_file(org, repo, branch, fn)
        sha = None
        if r:
            fileinfo = r.json()
            sha = fileinfo['sha']
            content = fileinfo['content']
        else:
            content = None
        new_content = base64.standard_b64decode(content).decode().splitlines() if content else []
        for a in lines:
            if a not in new_content:
                new_content.append(a)
        new_content = '\n'.join(new_content) + '\n'
        new_content = base64.standard_b64encode(new_content.encode()).decode()
        return self._update_file_content(org, repo, branch, fn, sha, content, new_content)

    def _update_file_content(self, org, repo, branch, fn, sha, content, new_content):
        if not sha or (content != new_content):
            data = {
                'branch' : branch,
                'content': new_content,
                }
            method = 'POST'
            if sha:
                data['sha'] = sha
                method = 'PUT'
            self.check(method, self.repo_path(org, repo) + '/contents/' + fn, json=data)

    def update_file(self, org, repo, branch, fn, new_content):
        r = self.get_file(org, repo, branch, fn)
        sha = None
        if r:
            fileinfo = r.json()
            sha = fileinfo['sha']
            content = fileinfo['content']
        else:
            content = None
        new_content = base64.standard_b64encode(new_content.encode()).decode()
        return self._update_file_content(org, repo, branch, fn, sha, content, new_content)

    def update_content(self, org, repo, branch, src, message, ignored_files=None):
        ign = ['.gitattributes', '.gitignore'] + (ignored_files if ignored_files else [])
        exc = ['.osc', '.git']
        r = self.check_get(self.repo_path(org, repo) + '/contents-ext', params={
            'ref': branch,
            'includes': 'lfs_metadata'
            })
        filelist = r.json()['dir_contents']
        files = {}
        for f in filelist:
            if f['name'] not in ign and f['name'] not in exc:
                files[f['name']] = f
        with tempfile.TemporaryDirectory() as tmpdirname:
            hasher = init_repo(tmpdirname, repo, 'whatever')
            rq = { 'branch' : branch, 'files' : [], 'message': message }
            for filename in list_files(src):
                pathname = os.path.join(os.getcwd(), src, filename)
                excluded = False
                for e in exc:
                    if filename.startswith(e + '/'):
                        excluded = True
                basename = os.path.basename(filename)
                if basename in ign or filename in exc or excluded:
                    continue
                with open(pathname, 'rb') as fd:
                    content = fd.read()
                if files.get(filename):
                    if files[filename].get('lfs_oid', None):
                        sha = hashlib.sha256(content).hexdigest()
                        reference = files[filename]['lfs_oid']
                    else:
                        sha = subprocess.check_output(['git', 'hash-object', pathname], cwd=hasher, universal_newlines=True).splitlines()[0]
                        reference = files[filename]['sha']
                if not files.get(filename) or reference != sha:
                    content = base64.standard_b64encode(content).decode()
                    frq = { 'content' : content, 'path' : filename}
                    if files.get(filename):
                        frq['operation'] = 'update'
                        frq['sha'] = files[filename]['sha']
                        self.log_progress('UPDATE %s\n' % (filename))
                    else:
                        frq['operation'] = 'create'
                        self.log_progress('CREATE %s\n' % (filename))
                    rq['files'].append(frq)
                files.pop(filename, None)
            for filename in sorted(files.keys()):
                frq = { 'path' : filename, 'operation' : 'delete', 'sha' : files[filename]['sha'] }
                rq['files'].append(frq)
                self.log_progress('DELETE %s\n' % (filename))
            if len(rq['files']) > 0:
                self.check_post(self.repo_path(org, repo) + '/contents', json=rq)

    def get_pr(self, org, repo, tgt, src):
        pr =  self.check_exists(self.repo_path(org, repo) + '/pulls/' + tgt + '/' + src)
        return pr.json() if pr else pr

    def open_pr(self, org, repo, tgt, src, text):
        text = list(text.splitlines())
        title = text[0]
        body = '\n'.join(text[1:])
        return self.check_post(self.repo_path(org, repo) + '/pulls', json={
            'base': tgt,
            'head': src,
            'title': title,
            'body': body,
            }).json()
