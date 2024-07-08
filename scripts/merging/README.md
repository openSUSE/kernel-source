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
