#!/bin/bash

# Add more information to CVEs that need fixing. This should be part of
# scripts/cve_tools/check-branch-status but we want to run that script
# in parallel for performance reasons and then we can easily hit bugzilla
# throttling even when we batch queries like in this script.
#
# scripts/cve_tools/check-branch-status output should be used as an input

add_age()
{
	local in="$1"
	local tmp_ages="$(mktemp)"
	local tmp_sed_pattern="$(mktemp)"
	local cves=""
	local now="$(date +%s)"

	# We need to prevent parallel runs from compeeting and triggering
	# the bugzilla rate limitting.
	grep -E "fix_missing|unapplied" $in | grep -Ev "code_disabled|unaffected|arch_disabled" | cut -d" " -f2 | xargs scripts/python/get-bugzilla-metadata -f cve,created,assignee,priority,status 2>/dev/null | sed 's@\(.*\);\(.*\) .*;\(.*\);\(P[0-9]\) .*;\(.*\)$@\1 \2 \3 \4 \5@' > $tmp_ages

	while read cve born assignee priority status
	do
		echo "s#\($cve.*\)#\1 $((($now - $(date -d $born +%s))/86400)) $assignee $priority $status#"
	done < $tmp_ages > $tmp_sed_pattern

	sed -i -f $tmp_sed_pattern $in
	rm $tmp_ages $tmp_sed_pattern
}

in="$1"
if [ ! -f "$in" ]
then
	in=$(mktemp)
	tmp_in=$in
	cat > $in
fi

add_age $in

if [ -n "$tmp_in" ]
then
	cat $tmp_in
	rm $tmp_in
fi
