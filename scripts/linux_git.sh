#!/bin/sh

# Determine the location of the mainline linux git repository to use as a
# reference by other scripts.

gitdir=${LINUX_GIT:-$HOME/linux-2.6}
if ! $(git -C "$gitdir" rev-parse --show-object-format 2>/dev/null >/dev/null); then
        echo "No linux git tree found (please set the \"LINUX_GIT\" environment variable)" >&2
        exit 1
fi
readlink -f "$gitdir"
