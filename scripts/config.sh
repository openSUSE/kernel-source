# SRCVERSION and VARIANT are set in rpm/config.sh
if test -e $(dirname -- "$0")/../rpm/config.sh; then
    source "$_"
elif test -e rpm/config.sh; then
    source "$_"
fi
BUILD_DIR=kernel-source${VARIANT}
IGNORE_ARCHS=
DIST_SET=11.4
