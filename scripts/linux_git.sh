#!/bin/sh

# Determine the location of the mainline linux git repository to use as a
# reference by other scripts.

gitdir=
for DIR in "$LINUX_GIT" "$HOME/linux-2.6" "$HOME/linux" "$HOME/linux.git"; do
	if [ -z "$DIR" -o ! -d "$DIR" ]; then
		continue
	fi

	cd "$DIR"
	BARE=$(git rev-parse --is-bare-repository 2>/dev/null)
	if [ $? -eq 0 ]; then
		if [ $BARE = "true" ]; then
			gitdir="$DIR"
		else
			gitdir="$DIR/.git"
		fi
		break
	fi
done

if [ -z "$gitdir" ]; then
        echo "No linux git tree found (please set the \"LINUX_GIT\" environment variable)" >&2
        exit 1
fi

if ! git rev-parse 1da177e4c3f4 &>/dev/null; then
        echo "Invalid linux git tree at \"$gitdir\" found (please set the \"LINUX_GIT\" environment variable)" >&2
        exit 1
fi

echo "$gitdir"
