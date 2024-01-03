# The version of the main tarball to use
SRCVERSION=6.4
# variant of the kernel-source package, either empty or "-rt"
VARIANT=
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
OBS_PROJECT=SUSE:ALP:Source:Standard:Core:1.0:Build
OBS_PROJECT_ARM=openSUSE:Factory:ARM
IBS_PROJECT=SUSE:ALP:Source:Standard:Core:1.0:Build
# Bugzilla info
BUGZILLA_SERVER="apibugzilla.suse.com"
BUGZILLA_PRODUCT="ALP"
SPLIT_OPTIONAL=No
SUPPORTED_MODULES_CHECK=Yes
# build documentation in HTML format
BUILD_HTML=Yes
# build documentation in PDF format
BUILD_PDF=No
