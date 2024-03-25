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

. scripts/common-functions

while [ $# -gt 0 ]
do
	arg=$1
	cve_sha="$(cd $VULNS_GIT; scripts/cve_search $arg 2>/dev/null | cut -d" " -f1,7)"
	cve=${cve_sha%% *}
	sha=${cve_sha##* }
	if [ $(echo $sha | wc -c) -eq 41 ]
	then
		echo -n "$sha"
		cvss="$(cve2cvss $cve)"
		echo -n " score:${cvss:-unknown}"
		bsc="$(cve2bugzilla $cve)"
		echo " $cve $bsc"
	else
		echo $arg not CVE nor sha >&2
	fi
	shift
done
