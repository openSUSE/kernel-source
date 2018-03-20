#!/bin/bash

_libdir=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")

sorted_section_changed () {
	status=$(git diff-index --cached --name-status --diff-filter=AM HEAD \
		-- "$_libdir"/../../series.conf | awk '{print $1}')
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
					"$_libdir"/series_conf.py
				) <(
				git cat-file blob :series.conf |
					"$_libdir"/series_conf.py
				) > /dev/null
			if [ $? -eq 1 ]; then
				return 0
			else
				return 1
			fi
			;;
	esac

	return 2
}

if sorted_section_changed && ! git cat-file blob :series.conf | \
	"$_libdir"/series_sort.py --check; then
	echo "\"sorted patches\" section of series.conf failed check. Please read \"scripts/git_sort/README.md\", in particular the section \"Refreshing the order of patches in series.conf\"."
	exit 1
fi
