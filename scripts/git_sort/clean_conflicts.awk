#!/usr/bin/awk -f

BEGIN {
	conflicts = 0
}

/^Conflicts:$/ {
	conflicts = 1
	getline
	next
}

/^---$/ {
	if (conflicts == 0) {
		print lastLine
	}
	conflicts = 2
}

{
	#print "statement 3 conflicts " conflicts $0
	if (conflicts == 0) {
		if (NR != 1) {
			print lastLine
		}
		lastLine = $0
	} else if (conflicts == 2) {
		print
	}
}
