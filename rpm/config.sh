# The version of the main tarball to use
SRCVERSION=5.3
# variant of the kernel-source package, either empty or "-rt"
VARIANT=-rt
# enable kernel module compression
COMPRESS_MODULES="xz"
# Use new style livepatch package names
LIVEPATCH=livepatch
# buildservice projects to build the kernel against
OBS_PROJECT=SUSE:SLE-15-SP1:Update
IBS_PROJECT=SUSE:SLE-15-SP2:Update
# Bugzilla info
BUGZILLA_SERVER="apibugzilla.suse.com"
BUGZILLA_PRODUCT="SUSE Linux Enterprise Server 15 SP2"
# Check the sorted patches section of series.conf
SORT_SERIES=yes
