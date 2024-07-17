## Usage

* Set `VULNS_GIT` environment variable to a clone of https://git.kernel.org/pub/scm/linux/security/vulns.git
* Set `KSOURCE_GIT` environment variable to a clone of kernel-source
  * Fetch the repo to base work on up-to-date branches
* Pick a working directory `WD` (will store working data)

* Run as
```
cd $WD
make -f path/to/scripts/cve_tools/Makefile BRANCH=cve/linux-5.14-LTSS update_refs_history

* Optionally with BASE_BRANCH (when different from origin/$BRANCH)
```
make -f path/to/scripts/cve_tools/Makefile BRANCH=SLE15-SP5 BASE_BRANCH=SLE15-SP5-with-cve-merged update_refs_history
```

* that will create a new git branch in `KSOURCE_GIT` and add commits with new
  references
* it will create git worktree in the `WD`
  * conversely `KSOURCE_GIT` cannot be a worktree (implementation issue)
* it will store processed data files in the `WD`
* the data can be reused with different BRANCH=

## TODO

* move working data from CWD to `XDG_CACHE_HOME` so that they can be used by
  other utils
* integrate with branches.conf so that list of "root" branches is extracted
* integrate with branches.conf so that non-root branches are handled too (easy
  if we allow multiplicities of RPM changelog messages)
