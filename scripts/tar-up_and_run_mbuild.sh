#!/bin/bash
#set -xev
echo "dont forget to update the defconfig files, or the mbuild may fail"
sleep 1
sudo -l
important_specfiles="default smp ppc64 iseries64 s390 s390x"
all_specfiles="`sed -e '/^\+/s@^.*/@@p;d' config.conf | sort -u | xargs echo`"
single_specfiles=
timestamp=
rpm_release_string=
tolerate_unknown_new_config_options=
external_modules=
dist=
specfiles=$important_specfiles
# action item: learn why $LOGNAME or $USER is not exported...
user="`id -nu`"
mbuild_options=
until [ "$#" = "0" ] ; do
    case "$1" in
    -rs)
      rpm_release_string="-rs $2"
      shift 2
      ;;
    -ts)
	timestamp=-ts
	shift
	;;
    -nf)
      tolerate_unknown_new_config_options=-nf
      shift
      ;;
    -nem)
      external_modules=-nem
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
    -s|--spec)
	single_specfiles="$single_specfiles $2"
	shift 2
	;;
    all)
	specfiles=$all_specfiles
	shift
	;;
    -h|--help|-v|--version)
	cat <<EOF

${0##*/} builds a kernel.rpm via mbuild for the following list of specfiles:
$specfiles

these options are recognized:
    -l <nisusername>   username to send mails after mbuild has finished
    -d <distsetname>   "distribution set" to build for
                       to get a complete list of possible options:
                       '/work/src/bin/mbuild -d'
    -D <distname>      "distribution name" to build for
                       to get a complete list of possible options:
                       '/work/src/bin/mbuild -D'
    -s|--spec <config> to build only this kernel-<config>.rpm (option may be specified more than once)
    all                to build a kernel.rpm for all configured .config files:
    $all_specfiles

the following 3 options are needed to build vanilla kernel with a stripped down series.conf:
    -rs <string>       to append specified string to rpm release number
    -ts                to use the current date as rpm release number
    -nf                to proceed if a new unknown .config option is found during make oldconfig
    -nem               to not build any external km_* module packages
    
example usage:
sudo $0 -l talk -D ppc -D x86_64 -ts
sudo $0 -l talk -d stable -ts -nf -nem
sudo $0 -l talk -d stable -s um -s s390x -D i386 -D s390x -ts -nf -nem

simple usage:
sudo $0 -l talk

EOF
	exit 1
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
if [ ! -z "$single_specfiles" ] ; then
specfiles=`echo $single_specfiles | sort | xargs echo`
fi
scripts/tar-up.sh $timestamp $tolerate_unknown_new_config_options $external_modules
cd kernel-source
for i in $specfiles
do
echo	sudo /work/src/bin/mbuild $mbuild_options --obey-doesnotbuild kernel-$i.spec
 	sudo /work/src/bin/mbuild $mbuild_options --obey-doesnotbuild kernel-$i.spec
done
