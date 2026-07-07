## Usage like a mergetool

    [mergetool "patch-references"]
        cmd = /path/to/kernel-source/scripts/merging/references $LOCAL $BASE $REMOTE $MERGED
        trustExitCode = true

When you encounter a merge conflict in patch, apply the tool to offending
patchfiles

    git status
    ...
            both modified:   patches.suse/drm-amd-amdgpu-fix-potential-memleak.patch
    
    git mergetool --tool=patch-references patches.suse/drm-amd-amdgpu-fix-potential-memleak.patch

## Usage like a mergedriver

The definitions are in scripts/extra-gitconfig, then utilize
scripts/install-git-drivers to enable drivers on available files.
