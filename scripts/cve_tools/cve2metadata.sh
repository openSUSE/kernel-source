#!/bin/bash
#
# Usage:
# cve2metadata.sh CVE-NUM[...CVE-NUM]
#
# expects:
# VULNS_GIT to point to vulns DB git tree (clone from https://git.kernel.org/pub/scm/linux/security/vulns.git)

if [ -z "$VULNS_GIT" -o ! -d "$VULNS_GIT" ]
then
	echo "VULNS_GIT should point to vulns git tree" >&2
	echo "clone from https://git.kernel.org/pub/scm/linux/security/vulns.git" >&2
	exit 1
fi

if [ -z "$CVEKERNELTREE" ]
then
	export CVEKERNELTREE=$LINUX_GIT
fi

. scripts/common-functions

while [ $# -gt 0 ]
do
	arg=$1
	shas="$(cve2sha $arg)"
	if [ -n "$shas" ]
	then
		cve=$arg
	else
		cve=$(sha2cve $arg)
		if [ -z $cve ]
		then
			echo $arg cannot be resolved to a CVE >&2
			shift
			continue
		fi
		shas="$(cve2sha $cve)"
	fi
	echo -n "$(echo $shas | tr "\n" " ")"
	cvss="$(cve2cvss $cve)"
	echo -n " score:${cvss:-unknown}"
	bsc="$(cve2bugzilla $cve)"
	echo " $cve $bsc"
	is_cve_rejected $cve && echo "W: $cve has been rejected" >&2
	shift
done
