#!/bin/sh

# Determine the location of the mainline linux git repository to use as a
# reference by other scripts.

gitdir=${LINUX_GIT:-$HOME/linux-2.6}
if ! cd "$gitdir" 2>/dev/null; then
	echo "Error: could not change to LINUX_GIT directory" >&2
	exit 1
fi
unset GIT_DIR
if ! result=$(git rev-parse --git-dir 2>/dev/null); then
        echo "No linux git tree found (please set the \"LINUX_GIT\" environment variable)" >&2
        exit 1
fi
readlink -f "$result"
