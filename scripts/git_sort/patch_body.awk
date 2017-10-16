#!/usr/bin/awk -f

# from quilt's patchfns

!body && /^(---|\*\*\*|Index:)[ \t][^ \t]|^diff -/ {
	body = 1
}

body {
	print
}
