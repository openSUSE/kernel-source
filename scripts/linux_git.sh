#!/bin/sh

# Determine the location of the mainline linux git repository to use as a
# reference by other scripts.

gitdir=${LINUX_GIT:-$HOME/linux-2.6}
if ! [ -d "$gitdir/.git" ]; then
        echo "No linux git tree found (please set the \"LINUX_GIT\" environment variable)" >&2
        exit 1
fi
echo "$gitdir"
