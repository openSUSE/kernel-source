# The version of the main tarball to use
SRCVERSION=6.1
# variant of the kernel-source package, either empty or "-rt"
VARIANT=-longterm
# enable kernel module compression
COMPRESS_MODULES="zstd"
COMPRESS_VMLINUX="xz"
# Compile binary devicetrees on master and stable branches.
BUILD_DTBS="Yes"
# Generate a _multibuild file
MULTIBUILD="Yes"
# Use new style livepatch package names
LIVEPATCH=livepatch
# buildservice projects to build the kernel against
OBS_PROJECT=openSUSE:Factory
IBS_PROJECT=SUSE:Factory:Head
# Bugzilla info
BUGZILLA_SERVER="apibugzilla.suse.com"
BUGZILLA_PRODUCT="openSUSE Tumbleweed"
