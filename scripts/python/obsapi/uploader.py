from kutil.config import get_kernel_projects, get_package_archs, read_source_timestamp
import xml.etree.ElementTree as ET
from obsapi.obsapi import OBSAPI
from obsapi.teaapi import TeaAPI
from obsapi.api import APIError
import subprocess
import tempfile
import sys
import re
import os

class UploaderBase:
    def upload(self, data, message):
        self.data = data
        sys.stderr.write('Updating .gitattributes to put tarballs into LFS.\n')
        self.tea.update_gitattr(self.user, self.upstream.repo, self.user_branch)
        sys.stderr.write('Updating branch %s with content of %s\n' % (self.user_branch, data))
        self.tea.update_content(self.user, self.upstream.repo, self.user_branch, data, message)
        self.commit = self.tea.repo_branches(self.user, self.upstream.repo)[self.user_branch]['commit']['id']
        sys.stderr.write('commit sha: %s\n' % (self.commit,))
        return self.commit

    def ignore_kabi(self):
        file = 'IGNORE-KABI-BADNESS'
        sys.stderr.write('Uploading %s\n' % (file,))
        self.tea.update_file(self.user, self.upstream.repo, self.user_branch, file, [])

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

    def get_qa_repo(self, r):
        return 'QA_' + r if r not in ['standard', 'pool'] else 'QA'

    def get_kernel_projects(self):
        projects = get_kernel_projects(self.data)
        if self.obs.url == 'https://api.suse.de':
            return projects['IBS']
        elif self.obs.url == 'https://api.opensuse.org':
            return projects['OBS']
        else:
            raise APIError('Getting build repositories not supported for %s' % (self.obs.url,))

    def get_project_repo_archs(self, limit_packages=None):
        architectures = get_package_archs(self.data, limit_packages)
        projects = self.get_kernel_projects()
        projects_meta = {}
        for k in projects.keys():
            p = projects[k]
            meta = self.obs.project_exists(p)
            projects_meta[k] = (p, meta.content if meta else meta)
        results = {}
        for k in projects_meta.keys():
            prj = projects_meta[k][0]
            meta = projects_meta[k][1]
            if meta:
                xml = ET.fromstring(meta)
                assert prj == xml.get('name')
                # The previous implementation iterates repositories sorted by name
                # That's fairly arbitrary other than it puts pool before standard
                # OBS sorts repositories in reverse-alphabetical order, use that to
                # iterate in the same order as before
                for r in reversed(list(xml.iter('repository'))):
                    name = r.get('name')
                    if not ( name in ['pool', 'standard'] or
                            # ports repository is only relevant for old style projects
                            # Newer projects may have such repository bu it's not usable
                            ( name == 'ports' and not re.compile(r'\b(openSUSE:Factory|ALP|SLFO)\b').search(prj)) or
                            # livepatch builds for SLE 15 are against maintenance projects
                            ( re.compile('^SUSE_.*_Update$').match(name) and re.compile('^SUSE:Maintenance:').match(prj))):
                        continue
                    archs = []
                    for a in r.iter('arch'):
                        a = a.text.strip()
                        assert '%' not in a  # will need to do macro expansion otherwise
                        if prj in ['openSUSE:Factory', 'openSUSE.org:openSUSE:Factory'] and a == 'i586': # i586 build disabled in Factory
                            continue
                        if a in architectures:
                            architectures.remove(a)
                            archs.append(a)
                    if len(archs) > 0:
                        if k == '':
                            k = name
                        if not results.get(k, None):
                            results[k] = {}
                        if not results[k].get(prj, None):
                            results[k][prj] = {}
                        results[k][prj][name] = archs
            else:
                raise APIError('Could not retrieve metadata for project %s' % (prj,))
        return results

    def prjmeta(self, limit_packages=None, rebuild=False, debuginfo=False, maintainers=[]):
        repo_archs = self.get_project_repo_archs(limit_packages)
        source_timestamp = read_source_timestamp(os.path.join(self.data, 'source-timestamp'))
        branch = source_timestamp.get('git branch', None)
        xml = ET.Element('project', name=self.project)
        e = ET.SubElement(xml, 'title')
        e.text = 'Kernel builds for branch ' + branch
        ET.SubElement(xml, 'description')
        if not maintainers:
            maintainers = []
        for m in maintainers:
            if self.obs.group_exists(m):
                ET.SubElement(xml, 'group', groupid=m, role='maintainer')
            elif self.obs.user_exists(m):
                ET.SubElement(xml, 'person', userid=m, role='maintainer')
            else:
                sys.stderr.write('User id "%s" does not exist at %s\n' % (m, self.obs.url));
        e = ET.SubElement(xml, 'build')
        ET.SubElement(e, 'enable')
        e = ET.SubElement(xml, 'publish')
        ET.SubElement(e, 'enable')
        publish = e
        e = ET.SubElement(xml, 'debuginfo')
        ET.SubElement(e, 'enable') if debuginfo else ET.SubElement(e, 'disable')
        repolist = []
        for r in repo_archs.keys():
            if rebuild:
                repo = ET.Element('repository', name=r)
            else:
                repo = ET.Element('repository', name=r, rebuild='local', block='local')
            repolist.append(repo)
            assert len(repo_archs[r]) == 1
            prj = list(repo_archs[r].keys())[0]
            assert len(repo_archs[r][prj]) == 1
            prj_repo = list(repo_archs[r][prj].keys())[0]
            ET.SubElement(repo, 'path', project=prj, repository=prj_repo)
            for a in repo_archs[r][prj][prj_repo]:
                arch = ET.SubElement(repo, 'arch')
                arch.text = a
            qa_repo = self.get_qa_repo(r)
            ET.SubElement(publish, 'disable', repository=qa_repo)
            repo = ET.Element('repository', name=qa_repo)
            repolist.append(repo)
            ET.SubElement(repo, 'path', project=self.project, repository=r)
            for a in repo_archs[r][prj][prj_repo]:
                arch = ET.SubElement(repo, 'arch')
                arch.text = a
        for r in sorted(repolist, key=lambda x: x.get('name'), reverse=True):
            xml.append(r)
        ET.indent(xml)
        return ET.tostring(xml, encoding='unicode')

class Uploader(UploaderBase):
    def __init__(self, api, upstream_project, user_project, package, reset_branch=False, logfile=None):
        self.package = package
        self.project = user_project
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
