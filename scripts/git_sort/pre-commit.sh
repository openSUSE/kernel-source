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
	# $1: sorted output of the names of patches in the current (staged)
	# sorted section, one per line (i.e. "$current_names").
	common=$(comm -12 <(
		git diff-index --cached --name-only --diff-filter=AMD HEAD | sort
		) <(echo "$1") | wc -l)

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

current_names=$(git cat-file blob :series.conf |
	"$_libdir"/series_conf --name-only | sort)

if sorted_section_changed || sorted_patches_changed "$current_names"; then
	# series_sort should examine the patches in the index, not the
	# working tree. Check them out.
	checkout_dir="$(git rev-parse --git-dir)/git-sort/pre-commit-checkout"
	manifest="$checkout_dir.manifest"
	mkdir -p "$checkout_dir"

	# "<name> <staged blob sha>" pairs for every patch in the current
	# sorted section
	staged_shas=$(echo "$current_names" | awk '{print ":" $0, $0}' |
		git cat-file --batch-check='%(rest) %(objectname)' | sort)

	# Patches whose (name, staged sha) pair isn't already recorded in the
	# manifest: new to the sorted section, or changed since the manifest
	# was last written -- on this branch or any other.
	changed_names=$(comm -23 <(echo "$staged_shas") <(
			sort "$manifest" 2> /dev/null
			) | awk '{print $1}')

	echo "$changed_names" |
		git checkout-index --quiet --force --prefix="$checkout_dir/" --stdin
	if [ $? -ne 0 ]; then
		echo "Error refreshing $checkout_dir." > /dev/stderr
		exit 1
	fi

	echo "$staged_shas" > "$manifest"

	git cat-file blob :series.conf |
		"$_libdir"/series_sort --check --prefix="$checkout_dir"
	retval=$?

	if [ $retval -ne 0 ]; then
		echo "\"sorted patches\" section of series.conf failed check. Please read \"scripts/git_sort/README.md\", in particular the section \"Refreshing the order of patches in series.conf\"."
		exit 1
	fi
fi
