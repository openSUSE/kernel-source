# The version of the main tarball to use
SRCVERSION=6.1
# variant of the kernel-source package, either empty or "-rt"
VARIANT=
# enable kernel module compression
COMPRESS_MODULES="zstd"
COMPRESS_VMLINUX="xz"
# Compile binary devicetrees on master and stable branches.
BUILD_DTBS="Yes"
# Use new style livepatch package names
LIVEPATCH=livepatch
# buildservice projects to build the kernel against
OBS_PROJECT=openSUSE:Factory
OBS_PROJECT_ARM=openSUSE:Factory:ARM
OBS_PROJECT_PPC=openSUSE:Factory:PowerPC
OBS_PROJECT_RISCV=openSUSE:Factory:RISCV
OBS_PROJECT_S390=openSUSE:Factory:zSystems
IBS_PROJECT=SUSE:Factory:Head
IBS_PROJECT_ARM=Devel:ARM:Factory
# Bugzilla info
BUGZILLA_SERVER="apibugzilla.suse.com"
BUGZILLA_PRODUCT="openSUSE Tumbleweed"
