# The version of the main tarball to use
SRCVERSION=5.16-11200-g1d1df41c5a33
# variant of the kernel-source package, either empty or "-rt"
VARIANT=
# Set to 1 if the tree does not contain any non-vanilla patches at all
VANILLA_ONLY=1
# enable kernel module compression
COMPRESS_MODULES="xz"
# Compile binary devicetrees on master and stable branches.
BUILD_DTBS="Yes"
# buildservice projects to build the kernel against
OBS_PROJECT=openSUSE:Factory
OBS_PROJECT_ARM=openSUSE:Factory:ARM
OBS_PROJECT_PPC=openSUSE:Factory:PowerPC
IBS_PROJECT=SUSE:Factory:Head
IBS_PROJECT_ARM=Devel:ARM:Factory
