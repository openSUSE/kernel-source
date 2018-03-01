#!/usr/bin/awk -f

# from quilt's patchfns

/^(---|\*\*\*|Index:)[ \t][^ \t]|^diff -/ {
	exit
}

{
	print
}

