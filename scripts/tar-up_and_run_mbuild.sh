#!/bin/bash
#set -xev
echo "dont forget to update the defconfig files, or the mbuild may fail"
sleep 1
sudo -l
important_specfiles="default smp pseries64 iseries64 s390 s390x 64k-pagesize sn2"
all_specfiles="`sed -e '/^\+/s@^.*/@@p;d' config.conf | sort -u`"
timestamp=
dist=
specfiles=$important_specfiles
# action item: learn why $LOGNAME or $USER is not exported...
user="`id -nu`"
mbuild_options=
until [ "$#" = "0" ] ; do
    case "$1" in
    -ts)
	timestamp=-ts
	shift
	;;
    -l)
	user="$2"
	shift 2
	;;
    -d|-D)
	mbuild_options="$mbuild_options $1 $2"
	shift 2
	;;
    all)
	specfiles=$all_specfiles
	shift
	;;
    *)
	shift
	;;
    esac
done
mbuild_options="-l $user $mbuild_options"
if [ ! -z "$dist" ] ; then
mbuild_options="$mbuild_options $dist"
fi
scripts/tar-up.sh $timestamp
cd kernel-source
for i in $specfiles
do
echo	sudo /work/src/bin/mbuild $mbuild_options --obey-doesnotbuild kernel-$i.spec
 	sudo /work/src/bin/mbuild $mbuild_options --obey-doesnotbuild kernel-$i.spec
done
