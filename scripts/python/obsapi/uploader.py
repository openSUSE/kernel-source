from kutil.config import get_kernel_projects, get_package_archs, get_source_timestamp, read_source_timestamp, get_kernel_project_package, list_files, list_specs
import xml.etree.ElementTree as ET
from obsapi.teaapi import TeaAPI, json_custom_dump
from obsapi.obsapi import OBSAPI
from obsapi.api import APIError
import subprocess
import tempfile
import difflib
import json
import sys
import re
import os

ignore_kabi_file = 'IGNORE-KABI-BADNESS'

class UploaderBase:
    def log_progress(self, string):
        if hasattr(self, 'progress') and self.progress:
            self.progress.write(string)

    def upload(self, message=None):
        if not message:
            message = get_source_timestamp(self.data)
        self.log_progress('Updating .gitattributes to put tarballs into LFS.\n')
        self.tea.update_gitattr(self.user, self.upstream.repo, self.user_branch)
        self.log_progress('Updating branch %s with content of %s\n' % (self.user_branch, self.data))
        self.tea.update_content(self.user, self.upstream.repo, self.user_branch, self.data, message, [ignore_kabi_file] if self.ignore_kabi_badness else None)
        self.commit = self.tea.repo_branches(self.user, self.upstream.repo)[self.user_branch]['commit']['id']
        self.log_progress('commit sha: %s\n' % (self.commit,))
        return self.commit

    def sync_url(self):
        return self.upstream.api + '/' + self.user + '/' + self.upstream.repo + '?trackingbranch=' + self.user_branch + '#' + self.commit

    def submit(self, message=None):
        return self._submit(self.upstream, message)

    def is_pr_open(self, upstream):
        return self.tea.is_pr_open(upstream.org, upstream.repo, upstream.branch, self.user + ':' + self.user_branch)

    def _submit(self, upstream, message=None):
        if not upstream.branch:
            raise APIError("No upstream branch to submit to.")
        pr = self.is_pr_open(upstream)
        if not pr:
            if not message:
                editor = os.environ.get('EDITOR', 'vi')
                with tempfile.NamedTemporaryFile(prefix=upstream.org + '.' + upstream.repo + '.' + upstream.branch + '.') as tmp:
                    subprocess.check_call([editor, tmp.name]);
                    with open(tmp.name, 'r') as f:
                        message = f.read()
            if not len(message) > 0:
                raise APIError('Non-empty PR message needed')
            self.log_progress('Creating PR for %s/%s %s from %s/%s %s\n' % (upstream.org, upstream.repo, upstream.branch, self.user, upstream.repo, self.user_branch))
            pr = self.tea.open_pr(upstream.org, upstream.repo, upstream.branch, self.user + ':' + self.user_branch, message)
        pr = pr['html_url']
        self.log_progress('%s\n' % (pr,))
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
        if hasattr(self, 'repo_archs'):
            return self.repo_archs
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
        self.repo_archs = results
        return results

    def prjmeta(self, limit_packages=None, rebuild=False, debuginfo=False, maintainers=[]):
        repo_archs = self.get_project_repo_archs(limit_packages)
        source_timestamp = read_source_timestamp(os.path.join(self.data, 'source-timestamp'))
        branch = source_timestamp.get('git branch', 'unknown')
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
                self.log_progress('User id "%s" does not exist at %s\n' % (m, self.obs.url));
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

    def prjconf(self, limit_packages=None, rpm_checks=False, debuginfo=False):
        is_qa_repo = '0'
        multibuild = '_multibuild' in list_files(self.data)
        repo_archs = self.get_project_repo_archs(limit_packages)
        package = get_kernel_project_package(self.data)[1]
        qa_packages = ['kernel-obs-qa', 'kernel-obs-build']
        for r in repo_archs.keys():
            is_qa_repo += '||("%%_repository" == "%s")' % (self.get_qa_repo(r),)
        result = []
        if '_constraints' not in list_files(self.data):
            disk_needed = 14 if debuginfo else 4
            result.append(
'''%%ifarch %%ix86 x86_64
Constraint: hardware:processors 8
%%endif
%%ifarch %%ix86 x86_64 ia64 ppc ppc64 ppc64le
Constraint: hardware:disk:size unit=G %i
%%else
Constraint: hardware:disk:size unit=G %i
%%endif''' % (disk_needed, disk_needed / 2))
        result.append('Substitute: kernel-dummy')
        if not rpm_checks:
            result.append('Substitute: rpmlint-Factory')
            result.append('Substitute: post-build-checks-malwarescan')
        result.append('Macros:')
        result.append('%is_kotd 1')
        if self.ignore_kabi_badness:
            result.append('%ignore_kabi_badness 1')
        result.append('%klp_ipa_clones 1')
        result.append('%%is_kotd_qa (%s)' % (is_qa_repo,))
        result.append(':Macros')
        if limit_packages:
            for p in limit_packages:
                l = p if not multibuild or p == package else package + ':' + p
                result.append('BuildFlags: onlybuild:%s' % (l,))
        else:
            result.append('BuildFlags: excludebuild:%s:kernel-obs-qa' % (package,))
            result.append('BuildFlags: excludebuild:kernel-obs-qa')
            result.append('BuildFlags: nouseforbuild:%s:kernel-obs-build' % (package,))
            result.append('BuildFlags: nouseforbuild:kernel-obs-build')
            result.append('%%if %s' % (is_qa_repo,))
            result.append('BuildFlags: !excludebuild:%s:kernel-obs-qa' % (package,))
            result.append('BuildFlags: !excludebuild:kernel-obs-qa')
            result.append('BuildFlags: onlybuild:%s:kernel-obs-qa' % (package,))
            result.append('BuildFlags: onlybuild:kernel-obs-qa')
            result.append('BuildFlags: onlybuild:kernel-obs-build.agg')
            result.append('BuildFlags: onlybuild:nonexistent-package')
            result.append('BuildFlags: !nouseforbuild:%s:kernel-obs-build' % (package,))
            result.append('BuildFlags: !nouseforbuild:kernel-obs-build')
            result.append('%endif')
        return '\n'.join(result) + '\n'

    def filter_limit_packages(self, packages):
        ext = ".spec"
        if not packages:
            packages = []
        packages = [p[0:-len(ext)] if p.endswith(ext) else p for p in packages]
        packages = packages + [ 'kernel-' + p for p in packages]
        filelist = list_files(self.data)
        packages = [p for p in packages if p + ext in filelist]
        return packages

    def create_project(self, maintainers=None, limit_packages=None, debuginfo=None, rpm_checks=None, rebuild=None):
        limit_packages = self.filter_limit_packages(limit_packages)
        self.log_progress('Creating %s...' % (self.project,))
        self.obs.create_project(self.project, meta=self.prjmeta(maintainers=maintainers, limit_packages=limit_packages, rebuild=rebuild, debuginfo=debuginfo),
                                       conf=self.prjconf(limit_packages=limit_packages, debuginfo=debuginfo, rpm_checks=rpm_checks))
        self.log_progress('ok\n')

    def pkgmeta(self):
        pkgmeta = ET.Element('package', name=self.package, project=self.project)
        title = ET.SubElement(pkgmeta, 'title')
        title.text = self.package
        ET.SubElement(pkgmeta, 'description')
        scmsync = ET.SubElement(pkgmeta, 'scmsync')
        scmsync.text = self.sync_url()
        ET.indent(pkgmeta)
        return ET.tostring(pkgmeta)

    def create_package(self, limit_packages=None):
        limit_packages = self.filter_limit_packages(limit_packages)
        repo_archs = self.get_project_repo_archs(limit_packages)
        multibuild = '_multibuild' in list_files(self.data)
        specs = list_specs(self.data)
        repo_archs = self.get_project_repo_archs(limit_packages)
        package = get_kernel_project_package(self.data)[1]
        self.log_progress('Creating %s/%s...' % (self.project, self.package))
        self.log_progress('ok\n')
        self.obs.create_package_meta(self.project, self.package, self.pkgmeta())
        kob = 'kernel-obs-build'
        kob_agg = kob + '.agg'
        self.log_progress('Aggregating %s/%s...' % (self.project, kob_agg))
        self.obs.create_package(self.project, kob_agg)
        aggxml = ET.Element('aggregatelist')
        agg = ET.SubElement(aggxml, 'aggregate', project = self.project)
        pkg = ET.SubElement(agg, 'package')
        pkg.text = kob
        pkg = ET.SubElement(agg, 'package')
        pkg.text = package + ':' + kob
        for r in repo_archs.keys():
            ET.SubElement(agg, 'repository', target=self.get_qa_repo(r), source=r)
            # default aggregetio is identity, target=source.
            # target with no souce disables aggregation
            ET.SubElement(agg, 'repository', target=r)
        ET.indent(aggxml)
        self.obs.upload_file(self.project, kob_agg, '_aggregate', ET.tostring(aggxml), 'application/xml')
        self.log_progress('ok\n')
        links = self.obs.list_package_links(self.project, self.package)
        if not multibuild:
            for s in specs:
                if s == package:
                    continue
                self.log_progress('Linking %s/%s...' % (self.project, s))
                self.obs.create_link(self.project, s, self.package)
                while s in links:
                    links.remove(s)
                self.log_progress('ok\n')
        for s in links:
            self.log_progress('Deleting %s/%s...' % (self.project, s))
            self.obs.delete_package(self.project, s)
            self.log_progress('ok\n')

    def set_git_maintainers(self, maintainers):
        maintfile = '_maintainership.json'
        self.log_progress('Getting scmsync for %s...' % (self.upstream_project,))
        prjrepo = self.obs.project_repo(self.upstream_project)
        self.log_progress('%s\n' % (repr(prjrepo),))
        if prjrepo:
            assert self.tea.url == prjrepo.api
            self.log_progress('Getting %s...' % (maintfile,))
            data = self.tea.get_file_data(prjrepo.org, prjrepo.repo, prjrepo.branch, maintfile)
            data_decoded = json.loads(data)
            assert json.loads(json_custom_dump(data_decoded)) == data_decoded
            current_maintainers = json.loads(data).get(self.package, [])
            if (maintainers and maintainers != current_maintainers) or (not maintainers and data_decoded != json_custom_dump(data_decoded)):
                if maintainers:
                    data_decoded[self.package] = maintainers
                data_massaged = json_custom_dump(data_decoded)
                sys.stderr.write('\n'.join(difflib.unified_diff(data.splitlines(), data_massaged.splitlines(), lineterm='')))
                self.fork_repo(prjrepo, True)
                self.log_progress('Updating %s.\n' % (maintfile,))
                self.tea.update_file(self.user, prjrepo.repo, self.user_branch, maintfile, data_massaged)
                commit = self.tea.repo_branches(self.user, prjrepo.repo)[self.user_branch]['commit']['id']
                self.log_progress('commit sha: %s\n' % (commit,))
                self._submit(prjrepo, 'Update ' + self.package + ' maintainer list.' if maintainers else
                'Normalize ' + maintfile + ' formatting\nThe ' + maintfile + ' formatting is not entirely consistent.\nMake the formatting uniform across the whole file to facilitate automated updates.')

    def fork_repo(self, upstream_repo, reset_branch):
        upstream_info = self.tea.repo_exists(upstream_repo.org, upstream_repo.repo)
        if upstream_info:
            upstream_info = upstream_info.json()
        downstream_info = self.tea.repo_exists(self.user, upstream_repo.repo)
        if downstream_info:
            downstream_info = downstream_info.json()
        if upstream_info and downstream_info:
            if not downstream_info['fork'] or downstream_info['parent']['full_name'] != upstream_repo.org + '/' + upstream_repo.repo:
                raise APIError('Fork of ' + upstream_repo.org + '/' + upstream_repo.repo + ' needed.')
        if upstream_repo.branch:
            assert upstream_repo.branch in self.tea.repo_branches(upstream_repo.org, upstream_repo.repo)
        if upstream_repo.commit:  # Maybe check it's part of the branch as well?
            self.tea.repo_commit_exists(upstream_repo.org, upstream_repo.repo, upstream_repo.commit)  # may be missing because of sync error
        if not downstream_info:
            if upstream_info:
                self.log_progress('Forking repository %s/%s from %s/%s.\n' % (self.user, upstream_repo.repo, upstream_repo.org, upstream_repo.repo))
            else:
                self.log_progress('Creating repository %s/%s.\n' % (self.user, upstream_repo.repo))
            downstream_info = self.tea.fork_repo(upstream_repo.org, self.user, upstream_repo.repo)
        if upstream_info and upstream_repo.branch:
            self.log_progress('Merging upstream branch %s..' % (upstream_repo.branch,))
            pull = self.tea.merge_upstream_branch(self.user, upstream_repo.repo, upstream_repo.branch)
            if not pull.ok:
                self.log_progress(' '.join([pull.status_message_pretty, repr(pull.json())]) + '\n')
            else:
                self.log_progress('ok\n')
        if self.is_pr_open(upstream_repo):
            reset_branch = False
        if not downstream_info['empty']:
            if reset_branch:
                self.log_progress('Resetting branch %s.\n' % (self.user_branch,))
            else:
                self.log_progress('Creating branch %s.\n' % (self.user_branch,))
            self.tea.create_branch(self.user, upstream_repo.repo, self.user_branch, upstream_repo.branch, upstream_repo.commit, reset_branch)


class Uploader(UploaderBase):
    def __init__(self, api, data, user_project, reset_branch=False, logfile=None, progress=True, ignore_kabi=False):
        self.progress = sys.stderr if progress else None
        self.data = data
        self.upstream_project, self.package = get_kernel_project_package(self.data)
        self.project = user_project.replace('/',':')
        self.obs = OBSAPI(api, logfile)
        self.log_progress('Getting scmsync for %s/%s...' % (self.upstream_project, self.package))
        self.upstream = self.obs.package_repo(self.upstream_project, self.package)
        self.log_progress('%s\n' % (repr(self.upstream),))
        self.tea = TeaAPI(self.upstream.api, logfile, progress=self.progress)
        self.log_progress('Getting Gitea user...')
        self.user = self.tea.get_user()
        self.log_progress('%s\n' % (self.user,))
        self.user_branch = user_project.translate(str.maketrans(':', '/')) if user_project else self.upstream.branch
        self.ignore_kabi_badness = ignore_kabi
        self.reset_branch = reset_branch
        self.fork_repo(self.upstream, self.reset_branch)
