SUSE Kernel Repository
======================


Overview
--------

The kernel-source repository contains sources, configuration files, package
definitions and supporting scripts for the SUSE kernels.

The SUSE kernels are generated from the upstream Linux kernel sources found at
<https://kernel.org/>, on top of which a number of patches are applied. The
expanded kernel source tree is configured and built, resulting in a binary
kernel.


Getting started
---------------

Make sure you have the git and quilt tools installed.

Introduce yourself if you haven't done so already:

    $ git config --global user.name "Your Name"
    $ git config --global user.email your@email

If you omit the `--global` option, the setting will only apply to this
repository clone.

Set up some Git hooks and helpers:

    $ ./scripts/install-git-hooks

To hack on the kernel sources:

    $ ./scripts/sequence-patch.sh
    $ cd tmp/linux-$version-$branch
    $ quilt new patches.suse/fix-foo-and-bar.patch
    $ quilt edit some/file.c
    $ ./refresh_patch.sh
    $ quilt header -e # see next chapter

Refer to the Quilt documentation for details. When you are done, add the new
patch to an appropriate place in the `series.conf` file and run `./scripts/log`
to commit it. Patches should be named such that they consist of alphanumeric
characters, '-' and '.'. Typically, patches are named by filtering the Subject
of the patch to a lower-case, dash-separated form like the one in the example
above.

To build RPM packages:

    $ ./scripts/tar-up.sh

This creates a source package in the kernel-source directory. Use

    $ ./scripts/osc_wrapper [kernel-source/kernel-$flavor.spec]

to build a kernel package locally, or

    $ ./scripts/osc_wrapper upload [--ibs]

to have all flavors and architectures built by the Open Build Service. The
`--ibs` option uses the SUSE internal instance.


Patch headers
-------------

Each patch must have an RFC822-style header that at a minimum describes what the
patch does, who wrote it and who inside SUSE can be contacted about problems
with the patch. The rules for patch headers are:

* Each patch must have a From tag that identifies the author of the patch.

* Each patch must have a Subject tag that briefly describes what the patch does.
  A brief summary that could appear in a change log makes the most sense in most
  cases.

* Unless the author specified in the From tag has a @suse.com, @suse.de or
  @suse.cz address, the patch must include a Signed-off-by, Acked-by or
  Reviewed-by header which identifies the person in one of these domains who
  feels responsible for the patch inside the company.

* The patch must include a Patch-mainline tag that identifies where the patch
  came from (for backports from mainline) or when it is expected to be added to
  mainline. The format is one of:

  For backports from mainline:

      Patch-mainline: <upstream version, for instance, "v6.5-rc7">
      Git-commit: <git hash>

  If the commit is from a maintainer repository or some other repository that
  isn't Linus's:

      Patch-mainline: Queued in subsystem maintainer repository
      Git-repo: <url>
      Git-commit: <git hash>

  If the patch is not upstream, depending on the situation:

      Patch-mainline: Submitted, <timestamp - destination>

      Patch-mainline: Not yet, <reason>

      Patch-mainline: Never, <reason>

* The patch should include a References tag that identifies the Bugzilla bug
  number, JIRA issue ID, etc. where the patch is discussed. Please prefix
  bugzilla.suse.com bug numbers with bsc# and JIRA issue IDs with jsc#. Make
  sure you specify a JIRA Implementation task when referencing JIRA features,
  not its Epic ID. Have a look at
  <https://en.opensuse.org/openSUSE:Packaging_Patches_guidelines#Current_set_of_abbreviations>
  for a full list of abbreviations.

* The patch header should include a more extensive description of what the patch
  does, why and how. The idea is to allow others to quickly identify what each
  patch is about and to give enough information for reviewing.

More details about valid patch headers can be found in
`scripts/patch-tag-template`. The helper script `scripts/patch-tag` can be used
for managing these tags. Documentation for `patch-tag` can be found at the top
of the script itself.

Example usage of `scripts/patch-tag-template`:

    $ cp scripts/patch-tag-template ~/.patchtag
    [ Edit ~/.patchtag with any default values you want. ]
    $ patch-tag -e file.diff

Example patch header:

```
From: Pablo Neira Ayuso <pablo@netfilter.org>
Date: Tue, 15 Aug 2023 15:39:01 +0200
Subject: netfilter: nf_tables: GC transaction race with netns dismantle
Patch-mainline: v6.5-rc7
Git-commit: 02c6c24402bf1c1e986899c14ba22a10b510916b
References: CVE-2023-4563 bsc#1214727

Use maybe_get_net() since GC workqueue might race with netns exit path.

Fixes: 5f68718b34a5 ("netfilter: nf_tables: GC transaction API to avoid race with control plane")
Signed-off-by: Pablo Neira Ayuso <pablo@netfilter.org>
Signed-off-by: Florian Westphal <fw@strlen.de>
Acked-by: Michal Kubecek <mkubecek@suse.cz>
```


Patch sorting
-------------

Patches added to the "sorted patches" section of `series.conf` must be sorted
according to the upstream order of the commits that they backport.

After you've added a patch file to the main `patches.suse/` or a different patch
directory, and supplemented the required tags described in the section [Patch
headers](#patch-headers), run

    $ ./scripts/git_sort/series_insert.py <patch>

to insert an entry for a new patch file to the sorted section of `series.conf`.

For more information, please read `scripts/git_sort/README.md`.


Before you commit -- things to check
------------------------------------

Make sure that all patches still apply after your changes. One way of doing this
is using `scripts/sequence-patch.sh`:

    $ export SCRATCH_AREA=/var/tmp/scratch
    $ ./scripts/sequence-patch.sh
    Creating tree in /var/tmp/scratch/linux-5.14-SLE15-SP5
    Cleaning up from previous run
    Linking from /var/tmp/scratch/linux-5.14.orig
    ...
    [ Tree: /var/tmp/scratch/linux-5.14-SLE15-SP5 ]
    [ Generating Module.supported ]
    [ Copying config/x86_64/default ]

Note the "Tree:" line output by the `sequence-patch.sh` script which specifies
the location of the expanded kernel tree that is configured for local build.
Please test-compile the kernel or even test-build kernel packages, depending on
the impact of your changes. Use `scripts/tar-up.sh` for creating an OBS package
directory.

The kernel source tree that `scripts/sequence-patch.sh` creates can be
test-compiled. Before that, make sure all prerequisites are installed. These
include libopenssl-devel, libelf-devel and dwarves. Have a look into
`rpm/kernel-binary.spec.in` for a complete list. Then, the compilation can be
done as follows:

    $ cd /var/tmp/scratch/linux-5.14-SLE15-SP5
    $ make oldconfig
    $ make

When committing a patch series, try to make the series easily bisectable. In
other words, when applying only the first x patches (1 <= x <= n, n being the
number of patches in the series), the kernel should be still buildable and
functional.

This means especially that just adding upstream patches unmodified to a series
and doing a cleanup patch at the end of the series to ensure the kernel is
buildable and functional is to be avoided. Each patch from upstream should be
modified as required to fit into the kernel it is backported to, both for build
time and runtime.

Applying all patches in the tree with `scripts/sequence-patch.sh` can take
a significant amount of time. The `--rapid` option is present to speed up the
process and tells the script to use Rapidquilt instead of the regular Quilt.
The Rapidquilt implementation applies patches in parallel and typically produces
an expanded tree in a fraction of the original time. A Rapidquilt package can be
obtained from <https://download.opensuse.org/repositories/Kernel:/tools/>.


Config option changes
---------------------

SUSE kernel packages for various architectures and configurations are built from
the same sources. Each such kernel has its own configuration file in
`config/$ARCH/$FLAVOR`. Checks are in place that abort the kernel build when
those configuration files are missing necessary config options.

When adding patches that introduce new kernel config options, please also update
all config files as follows:

    $ ./scripts/sequence-patch.sh
    $ cd /var/tmp/scratch/linux-5.14-SLE15-SP5
    $ ./patches/scripts/run_oldconfig.sh


Committing and log messages
---------------------------

Every commit to the kernel source repository should be properly documented.
Tool `scripts/tar-up.sh` obtains change descriptions from a Git commit log and
automatically produces `.changes` files for use by the target RPM packages. All
commits which affect the kernel package have their description collected, only
changes modifying internals of the repository such as helper scripts are
skipped.

When recording your changes to the repository, you should use `scripts/log`
rather than running `git commit` directly in order to produce a commit
description in the expected format.


What is the kernel ABI?
-----------------------

All symbols that the kernel exports for use by modules and all symbols that
modules export for use by other modules are associated with a so-called
modversion. It is a checksum of the type of the symbol, including all sub-types
involved. Symbols that a module imports are associated with the identical
checksum.

When a module is loaded, the kernel makes sure that the checksums of the symbols
imported by the module match the checksums of the target symbols. In case of
a mismatch, the kernel rejects to load the module.

Kernel packages additionally set an RPM dependency in the form
`ksym($FLAVOR:$SYMBOL) = $CHECKSUM` for every exported/imported symbol.
A Provides dependency is present for each symbol exported by kernel binaries in
the package and a Requires dependency is recorded for each imported symbol. This
mechanism allows checking module dependencies early at the package installation
time.


Kernel ABI changes
------------------

SUSE kernels maintain stable kABI during a lifetime of each service pack. An
exported symbol can be changed only if a strong reason arises.

When building an RPM kernel package, the build logic checks the modversions of
the resulting kernel and compares them against the reference stored in
`kabi/$ARCH/symvers-$FLAVOR` and `kabi/$ARCH/symtypes-$FLAVOR`. If any updated
or removed symbol is found, the build reports an error and aborts. Symbols
explicitly ignored in `kabi/severities` are excluded from this check. See
`rpm/kabi.pl` for details.

To update the reference files, use `scripts/update-symvers`:

    $ ./scripts/update-symvers kernel-default-5.14.21-150500.55.31.1.x86_64.rpm \
          kernel-default-devel-5.14.21-150500.55.31.1.x86_64.rpm ...

Updating the kabi files is typically done by the branch maintainers. Please
always ask them for permission before touching these files.


Ignoring kernel ABI changes
---------------------------

It might sometimes be needed to tolerate particular kernel ABI changes and not
abort the build. At the same time, you may not want to update the reference
symvers and symtypes files in order to monitor the relative changes.

A specific kernel can be marked so that kernel ABI changes are ignored. This is
done by creating a `kabi/$ARCH/ignore-$FLAVOR` file, for example,
`kabi/x86_64/ignore-default`. The kernel ABI checks are still performed, but the
build does not abort if a problem is found. The content of the ignore file does
not matter.

All kernel ABI changes in all kernel packages can be ignored by creating a file
called `IGNORE-KABI-BADNESS` in the `kernel-source/` sub-directory of the
repository that `scripts/tar-up.sh` creates. Doing this may occasionally be
necessary for PTF kernels.


Embargoed patches
-----------------

At certain times during development, the kernel may include "embargoed" patches,
which are patches that must not be made available to parties outside of SUSE
before an agreed-upon time. Such patches usually have a date of publication that
has been coordinated among Linux distributors and other stakeholders. These
patches must not be committed to the usual branches, because these are pushed to
a public mirror, but instead to a branch named with an \_EMBARGO suffix, for
example, SLE15-SP5\_EMBARGO. The KOTD scripts will testbuild such branches but
won't publish them. Once the fix becomes public, the branch needs to be merged
back into the "mainline" branch.


Related information
-------------------

Internal:

* <https://wiki.suse.net/index.php/SUSE-Labs_Publications/Kernel_Building>,
* <https://wiki.suse.net/index.php/SUSE-Labs_Publications/kernel_patches_rules>.

Public:

* <https://kernel.suse.com/>,
* <https://en.opensuse.org/Kernel>.
