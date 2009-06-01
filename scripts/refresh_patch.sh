#!/bin/sh
#
# keep noise between two revisions of a patch small:
# fixed sort order
# fixed filenames a/b, requires quilt 0.46+
# no timestamps
# diffstat to get a quick overview what files get modified
# 
export LC_ALL=C
export LANG=C
current=` quilt top `
case "$current" in
	*/patches.kernel.org/*)
	echo "Will not touch kernel.org patch '$current' because it will disappear soon."
	exit 0
	;;
	*);;
esac
quilt refresh \
	-U 3 \
	--no-timestamps \
	--no-index \
	--diffstat \
	--sort \
	--backup \
	-p ab
