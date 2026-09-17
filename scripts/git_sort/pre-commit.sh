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

# Computed once and reused below, instead of every caller re-running
# "series_conf" over the whole (possibly very large) sorted section.
current_names=$(git cat-file blob :series.conf |
	"$_libdir"/series_conf --name-only | sort)

if sorted_section_changed || sorted_patches_changed "$current_names"; then
	# series_sort should examine the patches in the index, not the
	# working tree. Check them out.
	#
	# Use a persistent checkout directory, reused across commits, rather
	# than a fresh temporary one. git_sort.SortIndex caches parsed patch
	# tags on disk, invalidated by each patch's mtime and size; checking
	# every patch out into a brand new directory every time gives all of
	# them a fresh mtime, defeating that cache and forcing every patch in
	# the sorted section to be reparsed on every commit. Reusing this
	# directory and only refreshing the patches that actually changed
	# lets unchanged patches keep their old mtime, so the cache can skip
	# reparsing them.
	checkout_dir="$(git rev-parse --git-dir)/git-sort/pre-commit-checkout"
	manifest="$checkout_dir.manifest"
	mkdir -p "$checkout_dir"

	# Patches whose staged content actually changed in this commit...
	changed_names=$(comm -12 <(
			git diff-index --cached --name-only --diff-filter=AM HEAD | sort
			) <(echo "$current_names"))
	# ...plus any patch not known to already be present in checkout_dir
	# (first use of this directory, or a name not seen since the
	# manifest was last written).
	missing_names=$(comm -23 <(echo "$current_names") <(
			sort "$manifest" 2> /dev/null
			))

	{ echo "$changed_names"; echo "$missing_names"; } | grep -v '^$' | sort -u |
		git checkout-index --quiet --force --prefix="$checkout_dir/" --stdin
	if [ $? -ne 0 ]; then
		echo "Error refreshing $checkout_dir." > /dev/stderr
		exit 1
	fi

	echo "$current_names" > "$manifest"

	git cat-file blob :series.conf |
		"$_libdir"/series_sort --check --prefix="$checkout_dir"
	retval=$?

	if [ $retval -ne 0 ]; then
		echo "\"sorted patches\" section of series.conf failed check. Please read \"scripts/git_sort/README.md\", in particular the section \"Refreshing the order of patches in series.conf\"."
		exit 1
	fi
fi
