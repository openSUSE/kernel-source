#!/bin/bash
set -e
ps3_patches=~/kernel/git/ps3-linux-patches
kernel_cvs=~/kernel/cvs/kernel-source-26
git_snapshot=

cd $ps3_patches

read git_snapshot < .git/refs/heads/master

echo "# PS3 git snapshot: $git_snapshot" >> $kernel_cvs/series.conf

for i in ` guards < series `
do
	patch="patches.arch/ppc-ps3tree-${i//\//_}"
	cp -v $i "$kernel_cvs/$patch"
	echo "	$patch" >> $kernel_cvs/series.conf
done
echo "# PS3 git snapshot end" >> $kernel_cvs/series.conf
