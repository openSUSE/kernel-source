# The version of the main tarball to use
SRCVERSION=6.4
# variant of the kernel-source package, either empty or "-rt"
VARIANT=-azure
# enable kernel module compression
COMPRESS_MODULES="zstd"
# Use new style livepatch package names
LIVEPATCH=livepatch
# Compile binary devicetrees for Leap
BUILD_DTBS="Yes"
# buildservice projects to build the kernel against
OBS_PROJECT=SUSE:SLE-15-SP7:GA
OBS_PROJECT_ARM=openSUSE:Step:15-SP5
IBS_PROJECT=SUSE:SLE-15-SP7:GA
# Bugzilla info
BUGZILLA_SERVER="apibugzilla.suse.com"
BUGZILLA_PRODUCT="SUSE Linux Enterprise Server 15 SP7"
# Check the sorted patches section of series.conf
SORT_SERIES=yes
# Modules not listed in supported.conf will abort the kernel build
SUPPORTED_MODULES_CHECK=Yes
# Split Leap-only modules to kernel-*-optional subpackage
SPLIT_OPTIONAL=Yes
# build documentation in HTML format
BUILD_HTML=Yes
# build documentation in PDF format
BUILD_PDF=No
# Generate compile_commands.json
GENERATE_COMPILE_COMMANDS=Yes
