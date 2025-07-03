# The version of the main tarball to use
SRCVERSION=6.12
# variant of the kernel-source package, either empty or "-rt"
VARIANT=-azure
# enable kernel module compression
COMPRESS_MODULES="zstd"
COMPRESS_VMLINUX="xz"
# Compile binary devicetrees on master and stable branches.
BUILD_DTBS="Yes"
# Generate a _multibuild file
MULTIBUILD="Yes"
# Use new style livepatch package names
LIVEPATCH=livepatch
# Enable livepatching related packages on -rt variant
LIVEPATCH_RT=1
# buildservice projects to build the kernel against
OBS_PROJECT=SUSE:SLFO:Main:Build
IBS_PROJECT=SUSE:SLFO:Main:Build
# Bugzilla info
BUGZILLA_SERVER="apibugzilla.suse.com"
BUGZILLA_PRODUCT="SUSE Linux Enterprise Server 16.0"
BUGZILLA_COMPONENT="Kernel"
SPLIT_OPTIONAL=Yes
SUPPORTED_MODULES_CHECK=Yes
# build documentation in HTML format
BUILD_HTML=Yes
# build documentation in PDF format
BUILD_PDF=No
# Generate compile_commands.json
GENERATE_COMPILE_COMMANDS=Yes
# Set gcc version to the one used for build in IBS
GCC_VERSION=13
# Use the new kABI tool
USE_SUSE_KABI_TOOLS=Yes
