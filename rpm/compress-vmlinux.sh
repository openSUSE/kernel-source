#!/bin/bash

set -x

# Once the brp script is reasonably widespread, we will remove the specfile
# hack and this script
if test -x /usr/lib/rpm/brp-suse.d/brp-99-compress-vmlinux; then
	exit 0
fi
vmlinux=$1
if test -e "$vmlinux" -a -e "$vmlinux.gz"; then
	# Deliberately not using gzip -n; the vmlinux image has a predictable
	# timestamp (bnc#880848#c20)
	gzip -k -9 -f "$vmlinux"
fi
