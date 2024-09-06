Installation Requirements
=========================
`git-sort` and the related series.conf sorting scripts depend on the python3
`dbm`, `pygit2`, and `PyYAML` modules.

For SLE12 SP5 python3-pygit2 package is available from the Kernel:tools OBS
project, for SLE15 and later where it's available from the OS update
repository.
```
https://build.opensuse.org/package/show/Kernel:tools/python-pygit2
```

series_merge_tool depends on `merge` from the rcs package, available in
standard repositories.

The functions in `quilt-mode.sh` are meant to be used with a modified `quilt`
that can use kernel-source.git's series.conf directly instead of a shadow
copy.

Packages are available Kernel:tools OBS project.
Source is avaible from
https://github.com/gobenji/quilt

quilt depends on diffstat from the package with the same name. For SLE12-SP2
and SLE12-SP3, the diffstat package is available in the SDK module.

Configuration Requirements
==========================
The LINUX_GIT environment variable must be set to the path of a fresh Linux
kernel git clone; it will be used as a reference for upstream commit
information. Specifically, this must be a clone of
git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git or one of the
alternate URLs found on kernel.org. The `user.name` and `user.email` git
config variables must be set to sensible values in that clone; they will be
used to tag patches.

If you want to import patches that are not yet in mainline but that are in a
subsystem maintainer's tree, that repository must be configured as an
additional remote of the local repository cloned under LINUX_GIT. For example:
```
linux$ git remote show
net # git://git.kernel.org/pub/scm/linux/kernel/git/davem/net.git
net-next # git://git.kernel.org/pub/scm/linux/kernel/git/davem/net-next.git
origin # git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
stable # git://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-stable.git
```

Inserting a new patch in the "sorted patches" section of series.conf
====================================================================
For a patch file, `<patch>` which is a backport of an upstream commit:
1) add the file into one of the `patches.*` directories
2) make sure that it contains the correct "Git-commit" tag
3) make sure that this commit can be found in your local LINUX_GIT clone

Then run:
```
kernel-source$ ./scripts/series_insert <patch>
```

This script can also be called with multiple patches at once.

Patches which are out-of-tree (not backports of upstream commits) can be added
directly at a location of your choosing in the "# out-of-tree" section of the
"sorted patches" section. In doubt, simply add them at the end of that section.

After the patch has been inserted in series.conf, make sure to check that the
series applies and to fix any potential conflicts. Then commit and push your
result.

Refreshing the order of patches in series.conf
==============================================
As upstream maintainers pull from each other, the order of patches in
series.conf needs to be refreshed. In that case, run:
```
kernel-source$ ./scripts/series_sort --upstream series.conf
```

In case of unexpected trouble, you can also move patch entries to the
"# out-of-tree" section and run the above script to reset a patch's position.

Backporting commits using kernel-source.git and the quilt-mode.sh functions
===========================================================================
The sections "Example workflow to backport a single commit" and "Example
workflow to backport a series of commits using kernel-source.git" demonstrate
how to use the functions in quilt-mode.sh, which can assist in backporting a
single commit or a series of commits directly to kernel-source.git.

Example workflow to backport a single commit
============================================
For example, we want to backport f5a952c08e84 which is a fix for another
commit which was already backported:
```
# adjust the path to `sequence-insert.py` according to your environment
ben@f1:~/local/src/kernel-source$ ./scripts/sequence-patch.sh $(./scripts/git_sort/sequence-insert.py f5a952c08e84)
[...]
ben@f1:~/local/src/kernel-source$ cd tmp/current
ben@f1:~/local/src/kernel-source/tmp/current$ . ../../scripts/git_sort/quilt-mode.sh
# Note that we are using the "-f" option of qcp since f5a952c08e84 is a
# followup to another commit; its log contains a "Fixes" tag. If that was not
# the case, we would use the "-d" and "-r" options of qcp.
ben@f1:~/local/src/kernel-source/tmp/current$ qcp -f f5a952c08e84
Info: using references "bsc#1026030 FATE#321670" from patch "patches.drivers/of-of_mdio-Add-a-whitelist-of-PHY-compatibilities.patch" which contains commit ae461131960b.
Importing patch /tmp/qcp.d82Wqi/0001-of-of_mdio-Add-marvell-88e1145-to-whitelist-of-PHY-c.patch (stored as patches/patches.drivers/of-of_mdio-Add-marvell-88e1145-to-whitelist-of-PHY-c.patch)
# Note that `q` is an alias for `quilt`. You may be using `q` a lot...
ben@f1:~/local/src/kernel-source/tmp/current$ q push
Applying patch patches/patches.drivers/of-of_mdio-Add-marvell-88e1145-to-whitelist-of-PHY-c.patch
File drivers/of/of_mdio.c is read-only; trying to patch anyway
patching file drivers/of/of_mdio.c
Applied patch patches/patches.drivers/of-of_mdio-Add-marvell-88e1145-to-whitelist-of-PHY-c.patch (needs refresh)

Now at patch patches/patches.drivers/of-of_mdio-Add-marvell-88e1145-to-whitelist-of-PHY-c.patch
ben@f1:~/local/src/kernel-source/tmp/current$ make olddefconfig
  HOSTCC  scripts/basic/fixdep
  HOSTCC  scripts/kconfig/conf.o
  SHIPPED scripts/kconfig/zconf.tab.c
  SHIPPED scripts/kconfig/zconf.lex.c
  SHIPPED scripts/kconfig/zconf.hash.c
  HOSTCC  scripts/kconfig/zconf.tab.o
  HOSTLD  scripts/kconfig/conf
scripts/kconfig/conf  --olddefconfig Kconfig
ben@f1:~/local/src/kernel-source/tmp/current$ qfmake
[...]
ben@f1:~/local/src/kernel-source/tmp/current$ ./refresh_patch.sh
Refreshed patch patches/patches.drivers/of-of_mdio-Add-marvell-88e1145-to-whitelist-of-PHY-c.patch
ben@f1:~/local/src/kernel-source/tmp/current$ cd ../../
ben@f1:~/local/src/kernel-source$ git st
On branch SLE12-SP3
Your branch is up-to-date with 'kerncvs/SLE12-SP3'.
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git checkout -- <file>..." to discard changes in working directory)

	modified:   series.conf

Untracked files:
  (use "git add <file>..." to include in what will be committed)

	patches.drivers/of-of_mdio-Add-marvell-88e1145-to-whitelist-of-PHY-c.patch

no changes added to commit (use "git add" and/or "git commit -a")
ben@f1:~/local/src/kernel-source$ git add -A
ben@f1:~/local/src/kernel-source$ ./scripts/log
```

Example workflow to backport a series of commits using kernel-source.git
========================================================================
Generate the list of commit ids to backport:
```
upstream$ git log --no-merges --topo-order --reverse --pretty=tformat:%H v3.12.6.. -- drivers/net/ethernet/emulex/benet/ > /tmp/output
```

Optionally, generate a description of the commits to backport.
```
upstream$ cat /tmp/output | xargs -n1 git log -n1 --oneline > /tmp/list
```

Optionally, check if commits in the list are referenced in the logs of later
commits which are not in the list themselves. You may wish to review these
later commits and add them to the list.
```
upstream$ cat /tmp/list | check_missing_fixes.sh
```

Optionally, check which commits in the list have already been applied to
kernel-source.git. Afterwards, you may wish to regenerate the list of commit
ids with a different starting point; or remove from series.conf the commits
that have already been applied and cherry-pick them again during the backport;
or skip them during the backport.

```
# note that the path is a pattern, not just a base directory
kernel-source$ cat /tmp/list | refs_in_series.sh "drivers/net/ethernet/emulex/benet/*"
```

Generate the work tree with patches applied up to the first patch in the
list of commits to backport:
```
# adjust the path to `sequence-insert` according to your environment
kernel-source$ ./scripts/sequence-patch.sh $(./scripts/git_sort/sequence-insert $(head -n1 /tmp/list | awk '{print $1}'))
```

It is preferable to check that the driver builds before getting started:
```
kernel-source/tmp/current$ make -j4 drivers/net/ethernet/intel/e1000/
```

Import the quilt-mode functions:
```
kernel-source/tmp/current$ . ../../scripts/git_sort/quilt-mode.sh
```

Set the list of commits to backport:
```
kernel-source/tmp/current$ qadd -r "bsc#1024371 FATE#321245" -d patches.drivers < /tmp/list
```

Note that the commits are automatically sorted using git-sort.
The references and destination are saved in environment variables and reused
later by `qcp` (see below). They can also be specified directly to `qcp`.

The working list can be queried at any time. Note that it is kept in the
$series environment variable. It will be lost if the shell exits. It is not
available in other terminals.
```
kernel-source/tmp/current$ qnext
847a1d6796c7 e1000: Do not overestimate descriptor counts in Tx pre-check (v4.6-rc3)
kernel-source/tmp/current$ qcat
	847a1d6796c7 e1000: Do not overestimate descriptor counts in Tx pre-check (v4.6-rc3)
	a4605fef7132 e1000: Double Tx descriptors needed check for 82544 (v4.6-rc3)
	1f2f83f83848 e1000: call ndo_stop() instead of dev_close() when running offline selftest (v4.7-rc1)
	91c527a55664 ethernet/intel: use core min/max MTU checking (v4.10-rc1)
	311191297125 e1000: use disable_hardirq() for e1000_netpoll() (v4.10-rc1)
```

Start backporting:
```
kernel-source/tmp/current$ qdoit -j4 drivers/net/ethernet/intel/e1000/
```

For each commit in the list, this command will
* go to the appropriate location in the series using `qgoto` which calls
  `quilt push/pop`
* check that the commit is not already present somewhere in the series using
  `qdupcheck`
* import the commit using `qcp` which calls `git format-patch` and `quilt
  import`
* add required tags using `clean_header.sh`
* apply the commit using `quilt push`
* build test the result using `qfmake`. This calls make with the options
  specified to `qdoit` plus the .o targets corresponding to the .c files
  changed by the topmost patch.

The process will stop automatically in case of error. At that time the user
must address the situation and then call `qdoit` again when ready.

To address the situation,
* if a commit is already present in an existing patch
	* possibly leave the patch where it is or move it to the current
	  location. To move a patch, edit series.conf. However, if the patch
	  is already applied, make sure to use `q pop` or `qgoto` first.
	  Then call `qskip` to skip the commit.
	* remove the other copy, using `q delete -r <patch`, then call
	  `qcp <commit>` and follow as indicated below (q push, qfmake,
	  ./refresh_patch.sh)
* if a commit does not apply
	`q push -f # or -fm`
	`vi-conflicts # also from git-helpers`
	`qfmake [...]`
	`./refresh_patch.sh`
* if one or more additional commits are necessary to fix the problem
	Use `qedit` to add these additional commits to the list of commits to
	backport.

	Note that the queue of commits to backport is sorted after invoking
	qadd or qedit. Therefore, commits can be added anywhere in the list
	when using qedit.
	After editing the queue of commits to backport, `qnext` will show one
	of the new commits since it should be backported before the current
	one. You can continue by calling `qdoit` to backport the dependent
	commits.
* if it turns out that the commit should be skipped
	`q delete -r`
	or, if after having done `q push -f`:
	`q pop -f`
	`q delete -r $(q next)`

The following commands can be useful to identify the origin of code lines when
fixing conflicts:
```
quilt annotate <file>
git gui blame --line=<line> <commit> <file>
```

Example of a merge conflict resolution involving sorted patches in series.conf
==============================================================================
When merging or rebasing between commits in kernel-source it is possible that
there is a conflict involving sorted patches in series.conf. This type of
conflict can be solved automatically using the git mergetool interface with
the script series_merge_tool. To set up the merge tool, add a section like this
to git config:

    [mergetool "git-sort"]
        cmd = scripts/series_merge_tool $LOCAL $BASE $REMOTE $MERGED
        trustExitCode = true

When using the merge tool, the LINUX_GIT reference repository must fetch from
the repositories which are the upstream source of patches which were added in
the remote branch of the merge (the `<commit>` argument to `git merge`) or
which are in different subsystem maintainer sections between the local and
remote revisions. A simple way to satisfy that condition is to fetch from all
remotes configured for git-sort before doing a merge resolution. The script
`scripts/git_sort/update_clone` can be used to create or update the
configuration of a repository so that it contains all of the remotes
configured for git-sort. Please see the help message of that script for more
information.

As an example, the merge in kernel-source commit da87d04b3b needed conflict
resolution. Let's redo this resolution using series_merge_tool:
```
ben@f1:~/local/src/kernel-source$ git log -n1 da87d04b3b
commit da87d04b3bc6edf2b58a10e27c77352a5eb7b3d9
Merge: e2d6a02d9c 1244565fb9
Author: Jiri Kosina <jkosina@suse.cz>
Date:   Wed Sep 13 18:48:33 2017 +0200

    Merge remote-tracking branch 'origin/users/dchang/SLE15/for-next' into SLE15

    Conflicts:
            series.conf
ben@f1:~/local/src/kernel-source$ git co e2d6a02d9c
HEAD is now at e2d6a02d9c... Merge remote-tracking branch 'origin/users/bpoirier/SLE15/for-next' into SLE15
ben@f1:~/local/src/kernel-source$ git merge 1244565fb9
Auto-merging series.conf
CONFLICT (content): Merge conflict in series.conf
Recorded preimage for 'series.conf'
Automatic merge failed; fix conflicts and then commit the result.
ben@f1:~/local/src/kernel-source$ git mergetool --tool=git-sort series.conf
Merging:
series.conf

Normal merge conflict for 'series.conf':
  {local}: modified file
  {remote}: modified file
10 commits added, 0 commits removed from base to remote.
ben@f1:~/local/src/kernel-source$ git st
HEAD detached at e2d6a02d9c
All conflicts fixed but you are still merging.
  (use "git commit" to conclude merge)

Changes to be committed:

        new file:   patches.drivers/be2net-Fix-UE-detection-logic-for-BE3.patch
        new file:   patches.drivers/be2net-Update-the-driver-version-to-11.4.0.0.patch
        new file:   patches.drivers/bnx2x-Remove-open-coded-carrier-check.patch
        new file:   patches.drivers/bnx2x-fix-format-overflow-warning.patch
        new file:   patches.drivers/net-broadcom-bnx2x-make-a-couple-of-const-arrays-sta.patch
        new file:   patches.drivers/net-phy-Make-phy_ethtool_ksettings_get-return-void.patch
        new file:   patches.drivers/netxen-fix-incorrect-loop-counter-decrement.patch
        new file:   patches.drivers/netxen-remove-writeq-readq-function-definitions.patch
        new file:   patches.drivers/netxen_nic-Remove-unused-pointer-hdr-in-netxen_setup.patch
        new file:   patches.drivers/qlge-avoid-memcpy-buffer-overflow.patch
        modified:   series.conf

Untracked files:
  (use "git add <file>..." to include in what will be committed)

        series.conf.orig

ben@f1:~/local/src/kernel-source$ git commit
```

Reporting Problems
==================
If you encounter problems while using any git-sort command, please send a
report to <kernel@suse.de> which includes the following information:
* the command you're trying to run and its output
* which kernel-source.git commit you are working on. If your tree has
  local changes before the command you're trying to run, commit them using
  `git commit -n` and push to a dummy user branch (ex:
  "users/<user>/SLE15/bugreport1") so that others can examine the tree and try
  to reproduce the issue.
* the output of
  kernel-source$ GIT_DIR=$LINUX_GIT scripts/git_sort/git_sort_debug -d
