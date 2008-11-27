#!/bin/bash
#set -xev
sudo -l
important_specfiles="default ppc64 s390 kdump vanilla ps3 xen"
all_specfiles="`sed -e '/^\+/s@^.*/@@p;d' config.conf | sort -u | xargs echo source dummy`"
single_specfiles=
timestamp=
rpm_release_string=
tolerate_unknown_new_config_options=
mbuild_no_checks=
dist=
prefer_rpms=
specfiles=$important_specfiles
# action item: learn why $LOGNAME or $USER is not exported...
user="`id -nu`"
mbuild_options=
with_debug=
ignore_kabi=
ignore_unsupported_deps=
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
	mbuild_no_checks=--no-checks
      shift
      ;;
    -l)
	user="$2"
	shift 2
	;;
    -d|-D)
	mbuild_options="$mbuild_options $1 $2"
	dist=yes
	shift 2
	;;
    -p|--prefer-rpms)
	prefer_rpms="--prefer-rpms $2"
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
    --debug)
      with_debug=$1
      shift
      ;;
    -i|--ignore-kabi)
        ignore_kabi=-i
        shift
        ;;
    -iu|--ignore-unsupported-deps)
        ignore_unsupported_deps=-iu
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
    -p|--prefer-rpms   to pass --prefer-rpms <directory> to mbuild
    -s|--spec <config> to build only this kernel-<config>.rpm (option may be specified more than once)
    --debug            to build a kernel-flavor-debug package with debug info for lkcd
                       requires MUCH diskspace
    -i|--ignore-kabi   ignore changes in the kabi
    -iu|--ignore-unsupported-deps
                       ignore supported modules depending on unsupported ones
    all                to build a kernel.rpm for all configured .config files:
    $all_specfiles

the following 3 options are needed to build vanilla kernel with a stripped down series.conf:
    -rs <string>       to append specified string to rpm release number
    -ts                to use the current date as rpm release number
    -nf                to proceed if a new unknown .config option is found during make oldconfig
    
example usage:
sudo $0 -l talk -D ppc -D x86_64 -ts
sudo $0 -l talk -d stable -ts -nf
sudo $0 -l talk -d stable -s s390x -D i386 -D s390x -ts -nf

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
mbuild_options="-l $user $mbuild_options $prefer_rpms $with_debug"
if [ -z "$dist" ] ; then
    source scripts/config.sh
    mbuild_options="$mbuild_options ${DIST_SET:+-d $DIST_SET}"
fi
if [ ! -z "$single_specfiles" ] ; then
specfiles=`echo $single_specfiles | sort | xargs echo`
fi
scripts/tar-up.sh $ignore_kabi $ignore_unsupported_deps $rpm_release_string $timestamp $tolerate_unknown_new_config_options || exit 1
cd kernel-source
for i in $specfiles
do
	/work/src/bin/tools/prepare_spec kernel-$i.spec > kernel-$i.spec.new
	mv kernel-$i.spec.new kernel-$i.spec
echo	sudo /work/src/bin/mbuild $mbuild_options $mbuild_no_checks --obey-doesnotbuild kernel-$i.spec
 	sudo /work/src/bin/mbuild $mbuild_options $mbuild_no_checks --obey-doesnotbuild kernel-$i.spec
done
