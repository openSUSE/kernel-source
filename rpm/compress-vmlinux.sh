#!/bin/bash

set -x

vmlinux=$1
if test -e "$vmlinux" -a -e "$vmlinux.gz"; then
	# Deliberately not using gzip -n; the vmlinux image has a predictable
	# timestamp (bnc#880848#c20)
	gzip -k -9 -f "$vmlinux"
fi
