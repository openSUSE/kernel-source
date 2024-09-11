#!/bin/bash

# Copyright (C) 2018 SUSE LLC
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

_libdir=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")

sorted_section_changed () {
	status=$(git diff-index --cached --name-status --diff-filter=AM HEAD \
		-- series.conf | awk '{print $1}')
	case "$status" in
		"")
			return 1
			;;
		A)
			return 0
			;;
		M)
			diff -q <(
				git cat-file blob HEAD:series.conf |
					"$_libdir"/series_conf
				) <(
				git cat-file blob :series.conf |
					"$_libdir"/series_conf
				) > /dev/null
			if [ $? -eq 1 ]; then
				return 0
			else
				return 1
			fi
			;;
	esac

	echo "Error detecting changes in series.conf sorted section." \
		> /dev/stderr
	return 2
}

sorted_patches_changed () {
	common=$(comm -12 <(
		git diff-index --cached --name-only --diff-filter=AMD HEAD | sort
		) <(
		git cat-file blob :series.conf |
			"$_libdir"/series_conf --name-only | sort
		) | wc -l)
	
	if ! [ "$common" -eq "$common" ] 2>/dev/stderr; then
		# not an integer
		echo "Error detecting changes in series.conf sorted patches." \
			> /dev/stderr
		return 2
	fi

	if [ $common -gt 0 ]; then
		return 0
	else
		return 1
	fi
}

if sorted_section_changed || sorted_patches_changed; then
	trap '[ -n "$tmpdir" -a -d "$tmpdir" ] && rm -r "$tmpdir"' EXIT
	tmpdir=$(mktemp --directory --tmpdir gs_pc.XXXXXXXXXX)

	# series_sort.py should examine the patches in the index, not the
	# working tree. Check them out.
	git cat-file blob :series.conf |
		"$_libdir"/series_conf --name-only |
		git checkout-index --quiet --prefix="$tmpdir/" --stdin

	git cat-file blob :series.conf |
		"$_libdir"/series_sort.py --check --prefix="$tmpdir"
	retval=$?

	rm -r "$tmpdir"
	unset tmpdir
	trap - EXIT

	if [ $retval -ne 0 ]; then
		echo "\"sorted patches\" section of series.conf failed check. Please read \"scripts/git_sort/README.md\", in particular the section \"Refreshing the order of patches in series.conf\"."
		exit 1
	fi
fi
