## Usage

* Set `VULNS_GIT` environment variable to a clone of https://git.kernel.org/pub/scm/linux/security/vulns.git
* Set `KSOURCE_GIT` environment variable to a clone of kernel-source
  * Fetch the repo to base work on up-to-date branches
* Pick a working directory `WD` (will store working data)

* Run as
```
cd $WD
make -f path/to/scripts/cve_tools/Makefile BRANCH=cve/linux-5.14-LTSS update_refs_history
```

* that will create a new git branch in `KSOURCE_GIT` and add commits with new
  references
* it is recommended that `KSOURCE_GIT` is not same directory where
  scripts/cve_tools/Makefile resides (e.g. use git worktrees)
  * conversely `KSOURCE_GIT` cannot be a worktree (implementation issue)
* it will store processed data files in the `WD`

## TODO

* move working data from CWD to `XDG_CACHE_HOME` so that they can be used by
  other utils
* integrate with branches.conf so that list of "root" branches is extracted
* integrate with branches.conf so that non-root branches are handled too (easy
  if we allow multiplicities of RPM changelog messages)
* `git --git-dir="$(VULNS_GIT)/.git" pull` is broken, it adds files to $WD when fresh pull
