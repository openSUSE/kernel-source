from obsapi.obsapi import OBSAPI
from obsapi.teaapi import TeaAPI
from obsapi.api import APIError
import subprocess
import tempfile
import sys
import os

class Uploader:
    def upload(self, data, message):
        sys.stderr.write('Updating .gitattributes to put tarballs into LFS.\n')
        self.tea.update_gitattr(self.user, self.upstream.repo, self.user_branch)
        sys.stderr.write('Updating branch %s with content of %s\n' % (self.user_branch, data))
        self.tea.update_content(self.user, self.upstream.repo, self.user_branch, data, message)
        self.commit = self.tea.repo_branches(self.user, self.upstream.repo)[self.user_branch]['commit']['id']
        sys.stderr.write('commit sha: %s\n' % (self.commit,))
        return self.commit

    def sync_url(self):
        return self.upstream.api + '/' + self.user + '/' + self.upstream.repo + '?trackingbranch=' + self.user_branch + '#' + self.commit

    def submit(self, message=None):
        if not self.upstream.branch:
            raise APIError("No upstream branch to submit to.")
        pr = self.tea.get_pr(self.upstream.org, self.upstream.repo, self.upstream.branch, self.user + ':' + self.user_branch)
        if not pr:
            if not message:
                editor = os.environ.get('EDITOR', 'vi')
                with tempfile.NamedTemporaryFile(prefix=self.upstream.org + '.' + self.upstream.repo + '.' + self.upstream.branch + '.') as tmp:
                    subprocess.check_call([editor, tmp.name]);
                    with open(tmp.name, 'r') as f:
                        message = f.read()
            if not len(message) > 0:
                raise APIError('Non-empty PR message needed')
            sys.stderr.write('Creating PR for %s/%s %s from %s/%s %s\n' % (self.upstream.org, self.upstream.repo, self.upstream.branch, self.user, self.upstream.repo, self.user_branch))
            pr = self.tea.open_pr(self.upstream.org, self.upstream.repo, self.upstream.branch, self.user + ':' + self.user_branch, message)
        pr = pr['html_url']
        sys.stderr.write('%s\n' % (pr,))
        return pr

    def __init__(self, api, upstream_project, user_project, package, reset_branch=False, logfile=None):
        self.package = package
        self.obs = OBSAPI(api, logfile)
        sys.stderr.write('Getting scmsync for %s/%s...' % (upstream_project, package))
        self.upstream = self.obs.package_repo(upstream_project, package)
        sys.stderr.write('%s\n' % (repr(self.upstream),))
        self.tea = TeaAPI(self.upstream.api, logfile)
        sys.stderr.write('Getting Gitea user...')
        self.user = self.tea.get_user()
        sys.stderr.write('%s\n' % (self.user,))
        self.user_branch = user_project.translate(str.maketrans(':', '/')) if user_project else self.upstream.branch
        upstream_info = self.tea.repo_exists(self.upstream.org, self.upstream.repo)
        if upstream_info:
            upstream_info = upstream_info.json()
        downstream_info = self.tea.repo_exists(self.user, self.upstream.repo)
        if downstream_info:
            downstream_info = downstream_info.json()
        if upstream_info and downstream_info:
            if not downstream_info['fork'] or downstream_info['parent']['full_name'] != self.upstream.org + '/' + self.upstream.repo:
                raise APIError('Fork of ' + self.upstream.org + '/' + self.upstream.repo + ' needed.')
        if self.upstream.branch:
            assert self.upstream.branch in self.tea.repo_branches(self.upstream.org, self.upstream.repo)
        if self.upstream.commit:  # Maybe check it's part of the branch as well?
            assert self.tea.repo_commit(self.upstream.org, self.upstream.repo, self.upstream.commit)
        if not downstream_info:
            if upstream_info:
                sys.stderr.write('Forking repository %s/%s from %s/%s.\n' % (self.user, self.upstream.repo, self.upstream.org, self.upstream.repo))
            else:
                sys.stderr.write('Creating repository %s/%s.\n' % (self.user, self.upstream.repo))
            downstream_info = self.tea.fork_repo(self.upstream.org, self.user, self.upstream.repo)
        if upstream_info and self.upstream.branch:
            sys.stderr.write('Merging upstream branch %s.\n' % (self.upstream.branch,))
            self.tea.merge_upstream_branch(self.user, self.upstream.repo, self.upstream.branch)
        if reset_branch:
            sys.stderr.write('Resetting branch %s.\n' % (self.user_branch,))
        else:
            sys.stderr.write('Creating branch %s.\n' % (self.user_branch,))
        self.tea.create_branch(self.user, self.upstream.repo, self.user_branch, self.upstream.branch, self.upstream.commit, reset_branch)
