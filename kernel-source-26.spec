#
# spec file for package kernel-source-26
#
# Copyright (c) 2002 SuSE Linux AG, Nuernberg, Germany.
# This file and all modifications and additions to the pristine
# package are under the same license as the package itself.
#
# Please submit bugfixes or comments via http://www.suse.de/feedback/
#

# neededforbuild  modutils
# usedforbuild    aaa_base acl attr bash bind9-utils bison cpio cpp cvs cyrus-sasl db devs diffutils e2fsprogs file filesystem fileutils fillup findutils flex gawk gdbm-devel glibc glibc-devel glibc-locale gpm grep groff gzip kbd less libacl libattr libgcc libstdc++ libxcrypt m4 make man mktemp modutils ncurses ncurses-devel net-tools netcfg pam pam-devel pam-modules patch permissions ps rcs readline sed sendmail sh-utils shadow strace syslogd sysvinit tar texinfo textutils timezone unzip util-linux vim zlib-devel autoconf automake binutils bzip2 cracklib gcc gdbm gettext libtool perl rpm zlib

Name:         kernel-source-26
License:      GPL
Provides:     linux
BuildRequires: modutils
Autoreqprov:  off
Summary:      The Linux kernel (the core of the Linux operating system)
Group:        Development/Sources
Requires:     make c_compiler
# rpm doesn't like '-' in Version ...
Version:      2.6.0test4
%define kversion 2.6.0-test4
Release:      0
Source0:      linux-%{kversion}.tar.bz2
Source10:     series.conf
Source11:     arch-symbols
Source12:     guards
Source20:     config.tar.bz2
Source21:     config.conf
Source100:    patches.arch.tar.bz2
Source101:    patches.fixes.tar.bz2
Source102:    patches.drivers.tar.bz2
Source103:    patches.rpmify.tar.bz2
Source104:    patches.uml.tar.bz2
Source105:    patches.suse.tar.bz2
%define ver_str %{kversion}-%release
BuildRoot:    %_tmppath/linux-%ver_str-build
Prefix:       /usr/src

%description
Linux Kernel sources with many Improvements and Fixes.

Authors:
--------
    Linus Torvalds <torvalds@transmeta.com>
    
    see /usr/src/linux/CREDITS for more details.


%prep
###################################################################
# This package builds the SuSE Linux kernel source tree by adding
# up the vanillia kernelsource, a lot of patches and kernel
# configuration.
#
# _target_cpu can be set manually with the --target=XXX option to
# rpm.  default _target_cpu is $RPM_ARCH
# you may use this to test build the package for say s390 on a ia32
# host
###################################################################

# Determine which symbols to use for controlling the patch/file
# selection mechanism.

export PATCH_ARCH=%_target_cpu

chmod +x %_sourcedir/arch-symbols
SYMBOLS="$(%_sourcedir/arch-symbols)"
if [ -z "$SYMBOLS" ]; then
    echo "Unsupported architecture \`$ARCH'" >&2
    exit 1
fi
if [ -e %_sourcedir/extra-symbols ]; then
    SYMBOLS="$SYMBOLS $(cat %_sourcedir/extra-symbols)"
fi
echo "Architecture symbol(s): $SYMBOLS"

# Write symbols to %_builddir/symbols so that other RPM sections
# can use the identical symbols. (Currently not needed!)
#echo $SYMBOLS > %_builddir/symbols

# Unpack all sources and patches

%setup -q -T -n config		-b 20
%setup -q -T -n patches.arch	-b 100
%setup -q -T -n patches.fixes	-b 101
%setup -q -T -n patches.drivers	-b 102
%setup -q -T -n patches.rpmify	-b 103
%setup -q -T -n patches.uml	-b 104
%setup -q -T -n patches.suse	-b 105

# the kernel source tree is unpacked last so that RPM_BUILD_DIR
# points to the right path, /usr/src/packages/BUILD/linux-%version
%setup -q -n linux-%{kversion}

# Apply the patches needed for this architecture.

chmod +x %_sourcedir/guards
for patch in $(%_sourcedir/guards $SYMBOLS < %_sourcedir/series.conf); do
    if ! patch -s -E -p1 --no-backup-if-mismatch -i ../$patch; then
	echo "*** Patch $patch failed ***"
	exit 1
    fi
done

# config_subst makes sure that CONFIG_CFGNAME and CONFIG_RELEASE are
# set correctly.

config_subst()
{
    local name=$1 release=$2
    awk '
	function print_name(force)
	{
	    if (!done_name || force)
		printf "CONFIG_CFGNAME=\"%s\"\n", "'"$name"'"
	    done_name=1
	}
	function print_release(force)
	{
	    if (!done_release || force)
		printf "CONFIG_RELEASE=%d\n", '"$release"'
	    done_release=1
	}

	/\<CONFIG_CFGNAME\>/	{ print_name(1) ; next }
	/\<CONFIG_RELEASE\>/	{ print_release(1) ; next }
				{ print }
	END			{ print_name(0) ; print_release(0) }
    '
    #echo "CONFIG_MODVERSIONS=y"
}

# Install all config files that make sense for that particular
# kernel.

for config in $(%_sourcedir/guards $SYMBOLS < %_sourcedir/config.conf); do
    name=$(basename $config)
    path=arch/$(dirname $config)/defconfig.$name
    mkdir -p $(dirname $path)
    if [ "${config/*\//}" = "default" ]; then
        config_subst $name %release \
	    < %_builddir/config/$config \
	    > ${path%.default}
    fi
    config_subst $name %release \
	< %_builddir/config/$config \
	> $path
done
chmod +x arch/ia64/scripts/toolchain-flags


%build
###################################################################
export RPM_TARGET=%_target_cpu
case $RPM_TARGET in
i?86)
    RPM_TARGET=i386 ;;
esac

if [ "$RPM_TARGET" != "$HOSTTYPE" ]; then
    echo "CONFIG_CROSSCOMPILE=y" >> .config
    MAKE_ARGS="ARCH=$RPM_TARGET"
fi
yes "" | make $MAKE_ARGS oldconfig

make -s $MAKE_ARGS include/linux/version.h

# Collect the filelist. (Not needed at the moment.)
#find . -mindepth 1 -not -path ./linux.files > linux.files


%install
###################################################################
export RPM_TARGET=%_target_cpu
case $RPM_TARGET in
i?86)
    RPM_TARGET=i386 ;;
esac

if [ "$RPM_TARGET" != "$HOSTTYPE" ]; then
    MAKE_ARGS="$MAKE_ARGS ARCH=$RPM_TARGET"
fi

# Set up $RPM_BUILD_ROOT

rm -rf $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/usr/src/linux-%ver_str
ln -sf linux-%ver_str $RPM_BUILD_ROOT/usr/src/linux
#cpio -p $RPM_BUILD_ROOT/usr/src/linux-%ver_str < linux.files
cp -dpR --parents . $RPM_BUILD_ROOT/usr/src/linux-%ver_str

# Do a test build to catch the most stupid mistakes early.

if [ ! -e %_sourcedir/skip-build ]; then
make $MAKE_ARGS vmlinux
fi


%files
/usr/src/linux
/usr/src/linux-%ver_str
