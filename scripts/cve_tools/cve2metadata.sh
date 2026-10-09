#!/bin/bash
#
# Usage:
# cve2metadata.sh [-s] CVE-NUM|sha[...CVE-NUM]
#
# with -s prints short-sha ("subject")
#
# expects:
# VULNS_GIT to point to vulns DB git tree (clone from https://git.kernel.org/pub/scm/linux/security/vulns.git)
# LINUX_GIT to point to Linus git tree (clone from https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git)

if [ -z "$VULNS_GIT" -o ! -d "$VULNS_GIT" ]
then
	echo "VULNS_GIT should point to vulns git tree" >&2
	echo "clone from https://git.kernel.org/pub/scm/linux/security/vulns.git" >&2
	exit 1
fi
SCRIPTS_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/..
LINUX_GIT=$("$SCRIPTS_DIR"/linux_git.sh) || exit 1

. $SCRIPTS_DIR/common-functions

print_short=0
if [ "$1" = "-s" ]
then
	print_short=1
	shift
fi

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
			if [ $print_short -ne 0 ]
			then
				git --no-pager -C $LINUX_GIT show -s --pretty='format:%h ("%s")%n' $arg
			else
				echo $arg cannot be resolved to a CVE >&2
			fi
			shift
			continue
		fi
		shas="$(cve2sha $cve)"
	fi
	if [ $print_short -eq 0 ]
	then
		echo -n "$(echo $shas | tr "\n" " " | xargs $sha_cmd)"
	else
		echo -n "$(echo $shas | xargs git --no-pager -C $LINUX_GIT show -s --pretty='format:%h ("%s")')"
	fi
	cvss="$(cve2cvss $cve)"
	echo -n " score:${cvss:-unknown}"
	bsc="$(cve2bugzilla $cve)"
	echo " $cve $bsc"
	is_cve_rejected $cve && echo "W: $cve has been rejected" >&2
	shift
done
