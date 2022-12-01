# The version of the main tarball to use
SRCVERSION=5.14
# variant of the kernel-source package, either empty or "-rt"
VARIANT=-rt
# enable kernel module compression
COMPRESS_MODULES="zstd"
# Use new style livepatch package names
LIVEPATCH=livepatch
# Enable livepatching related packages on -rt variant
LIVEPATCH_RT=1
# Compile binary devicetrees for Leap
BUILD_DTBS="Yes"
# buildservice projects to build the kernel against
OBS_PROJECT=SUSE:SLE-15-SP4:Update
OBS_PROJECT_ARM=openSUSE:Step:15-SP4
IBS_PROJECT=SUSE:SLE-15-SP4:Update
# Bugzilla info
BUGZILLA_SERVER="apibugzilla.suse.com"
BUGZILLA_PRODUCT="SUSE Linux Enterprise Server 15 SP4"
# Check the sorted patches section of series.conf
SORT_SERIES=yes
