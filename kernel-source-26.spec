#
# spec file for package kernel-source (Version 2.4.20.SuSE)
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
Provides:     kernel linux
BuildRequires: modutils
Autoreqprov:  off
Summary:      The Linux kernel (the core of the Linux operating system)
Group:        Development/Sources
Requires:     make c_compiler
Version:      2.5.69.SuSE
Release:      0
%define kernel_version	2.5.69
%define lxsubdir	linux-%{kernel_version}
Source0:      linux-%{kernel_version}.tar.bz2
Source10:     series.conf
Source11:     arch-symbols
Source12:     guards
Source20:     config.tar.bz2
Source21:     config.conf
Source100:    patches.arch.tar.bz2
Source101:    patches.fixes.tar.bz2
Source102:    patches.drivers.tar.bz2
BuildRoot:    %{_tmppath}/%{name}-%{version}-build

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
# The %%prep step unpacks all patches, the SuSE default kernel
# configuration and the kernel source itself.  Then the patches to
# be applied for this architecture are collected into a common
# directory /usr/src/packages/BUILD/patches.
# The %%build step applies the patches in the _alphabetical_ order
# of their basename.  Patching is done in %%build, because patching
# is the real build in this package.
# The %%install step copies the patched kernel to $RPM_BUILD_ROOT
# and does a test build of the kernel with the SuSE default
# configuration for the current architecture, to see if everything
# is consistent.
###################################################################
# _target_cpu can be set manually with the --target=XXX option to
# rpm.  default _target_cpu is $RPM_ARCH
# you may use this to test build the package for say s390 on a ia32
# host
###################################################################


###################################################################
# determine which symbols to use for controlling the patch/file
# selection mechanism.
###################################################################

PATCH_ARCH=%{_target_cpu}
export PATCH_ARCH

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

# Write symbols to %{_builddir}/symbols so that other RPM sections
# can use the identical symbols. (Currently not needed!)
#echo $SYMBOLS > %{_builddir}/symbols

###################################################################
# unpack all sources and patches
###################################################################

# AG: Has the following define an effect?
%define _bzip2   bzip2 -dc

%setup -T -n config		-b 20
%setup -T -n patches.arch	-b 100
%setup -T -n patches.fixes	-b 101
%setup -T -n patches.drivers	-b 102

# the kernel source tree is unpacked last so that RPM_BUILD_DIR
# points to the right path, /usr/src/packages/BUILD/%lxsubdir
%setup -q -n %lxsubdir

###################################################################
# apply the patches needed for this architecture
###################################################################

chmod +x %_sourcedir/guards
for patch in `%_sourcedir/guards $SYMBOLS < %_sourcedir/series.conf`; do
    if ! patch -s -E -p1 --no-backup-if-mismatch -i ../$patch; then
	echo "*** Patch $patch failed ***"
	exit 1
    fi
done

###################################################################
# install all config files that make sense for that particular
# kernel
###################################################################

for config in `%_sourcedir/guards $SYMBOLS < %_sourcedir/config.conf`; do
	path=arch/$(dirname $config)/defconfig.$(basename $config)
	mkdir -p $(dirname $path)
	if [ "${config/*\//}" = "default" ]; then
		cp %_builddir/config/$config $path
		cp %_builddir/config/$config ${path%.default}
	else
		cp %_builddir/config/$config $path
	fi
done


%build
###################################################################
RPM_TARGET=%{_target_cpu}
if [ "$RPM_TARGET" = "i586" -o "$RPM_TARGET" = "i686" ] ; then
   RPM_TARGET=i386
fi
export RPM_TARGET
###################################################################
%ifnarch ppc
rm -fv bk.changes.txt changeset.txt
%endif
if [ "$RPM_TARGET" != "$HOSTTYPE" ]; then
 echo "CONFIG_CROSSCOMPILE=y" >> .config
  yes "" | make ARCH=$RPM_TARGET oldconfig
else
  yes "" | make oldconfig
fi
###################################################################

%install
###################################################################
RPM_TARGET=%{_target_cpu}
if [ "$RPM_TARGET" = "i586" -o "$RPM_TARGET" = "i686" ] ; then
   RPM_TARGET=i386
fi
export RPM_TARGET
###################################################################
# set up $RPM_BUILD_ROOT
rm -rf $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/usr/src/linux-%{version}
ln -s linux-%{version} $RPM_BUILD_ROOT/usr/src/linux
cp -a . $RPM_BUILD_ROOT/usr/src/linux-%{version}
###################################################################
# collect the filelist
{
    echo $RPM_BUILD_ROOT/usr/src/linux
    find $RPM_BUILD_ROOT/usr/src/linux-%{version} \
	 -path $RPM_BUILD_ROOT/usr/src/linux-%{version}/.config \
	 -o -path $RPM_BUILD_ROOT/usr/src/linux-%{version}/Documentation -prune -printf "%%%%doc %%p\n" \
	 -o -type d -printf "%%%%dir %%p\n" -o -print
    echo $RPM_BUILD_ROOT/usr/src/linux-%{version}/include/linux/version.h
    if grep -q CONFIG_MODVERSIONS=y .config; then
        echo "$RPM_BUILD_ROOT/usr/src/linux-%{version}/include/linux/modules/*.ver"
    fi
%ifarch x86_64
    echo $RPM_BUILD_ROOT/usr/src/linux-%{version}/include/asm/offset.h
%endif
} |
sed -e "s:$RPM_BUILD_ROOT::" > $RPM_BUILD_DIR/%lxsubdir/linux.files
###################################################################
# do a test build
cd $RPM_BUILD_ROOT/usr/src/linux-%{version}
if [ "$RPM_TARGET" != "$HOSTTYPE" ]; then
 ARG="ARCH=$RPM_TARGET"
 case $RPM_TARGET in s390*) ARG="$ARG CROSS_COMPILE=$RPM_TARGET-linux-";;esac
else 
 ARG=""
fi
if [ ! -e %_sourcedir/skip-build ]; then
make $ARG dep
# ARCHITECTURE DEPENDENT test build
%ifarch %ix86 x86_64
make $ARG $ARG2 bzImage
%endif
%ifarch alpha sparc sparc64
make $ARG boot
%endif
%ifarch ia64 ppc ppc64 mips
make $ARG vmlinux
%endif
%ifarch mips64
make $ARG vmlinux.64
%endif
%ifarch s390 s390x
 let GCCMEM="12*1024*1024"; set -- `sed -n '2{p;q;}' /proc/meminfo`
 let MEM="$2-55*1024*1024"; let PARALLEL_BY_RAM="$MEM/$GCCMEM"
 PARALLEL_BY_CPU=$(grep -c ^processor /proc/cpuinfo)
 PARALLEL=-j$(($PARALLEL_BY_RAM < $PARALLEL_BY_CPU ?
               $PARALLEL_BY_RAM : $PARALLEL_BY_CPU))
 make $ARG $PARALLEL image   || { echo ok, restarting; make $ARG image; }
 make $ARG $PARALLEL modules || { echo ok, restarting; make $ARG modules; }
 mv /lib/modules/%{kernel_version} /lib/modules/%{kernel_version}.42.42 || :
 make modules_install INSTALL_MOD_PATH=%buildroot
%endif
else
 make $(/bin/pwd)/include/linux/modversions.h
 make $(/bin/pwd)/include/linux/version.h
fi

%clean
if [ -s %_sourcedir/k_smp.tgz ]; then
	cd %_sourcedir
	tar xvfz k_smp.tgz
	ln -s k_smp/* .
	old /usr/src/linux-%{version} /usr/src/linux
	cp -a $RPM_BUILD_ROOT/usr/src/linux* /usr/src
	rpm -bb k_smp.spec
	cd -
fi

%files -f linux.files

