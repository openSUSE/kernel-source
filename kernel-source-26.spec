#
# spec file for package kernel-source-26 (Version 2.6.0_test8)
#
# Copyright (c) 2003 SuSE Linux AG, Nuernberg, Germany.
# This file and all modifications and additions to the pristine
# package are under the same license as the package itself.
#
# Please submit bugfixes or comments via http://www.suse.de/feedback/
#

# norootforbuild
# neededforbuild  modutils
# usedforbuild    aaa_base acl attr bash bind-utils bison bzip2 coreutils cpio cpp cvs cyrus-sasl db devs diffutils e2fsprogs file filesystem fillup findutils flex gawk gdbm-devel glibc glibc-devel glibc-locale gpm grep groff gzip info insserv kbd less libacl libattr libgcc libstdc++ libxcrypt m4 make man mktemp modutils ncurses ncurses-devel net-tools netcfg openldap2-client openssl pam pam-devel pam-modules patch permissions popt ps rcs readline sed sendmail shadow strace syslogd sysvinit tar texinfo timezone unzip util-linux vim zlib zlib-devel autoconf automake binutils cracklib gcc gdbm gettext libtool perl rpm

Name:         kernel-source-26
License:      GPL
Provides:     linux
BuildRequires: modutils
Autoreqprov:  off
Summary:      The Linux kernel (the core of the Linux operating system)
Group:        Development/Sources
Requires:     make c_compiler
PreReq:       %insserv_prereq
Version:      2.6.0_test11
Release:      0
%define kversion %(echo %version | sed s/_/-/g)
Source0:      http://www.kernel.org/pub/linux/kernel/v2.6/linux-%{kversion}.tar.bz2
Source10:     series.conf
Source11:     arch-symbols
Source12:     guards
Source20:     config.tar.bz2
Source21:     config.conf
Source30:     config_subst.sh
Source31:     merge-headers
Source32:     running-kernel.init.in
Source100:    patches.arch.tar.bz2
Source101:    patches.fixes.tar.bz2
Source102:    patches.drivers.tar.bz2
Source103:    patches.rpmify.tar.bz2
Source104:    patches.uml.tar.bz2
Source105:    patches.suse.tar.bz2
%define ver_str %{kversion}-%release
BuildRoot:    %{_tmppath}/%{name}-%{version}-build
Prefix:       /usr/src
# do not waste space on the CDs and on the mirrors
%ifarch ppc
NoSource:     0
%endif

%description
Linux Kernel sources with many fixes and improvements.



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

# Unpack all sources and patches
%setup -q -T -n config		-b 20
%setup -q -T -n patches.arch	-b 100
%setup -q -T -n patches.fixes	-b 101
%setup -q -T -n patches.drivers	-b 102
%setup -q -T -n patches.rpmify	-b 103
%setup -q -T -n patches.uml	-b 104
%setup -q -T -n patches.suse	-b 105

# The kernel source tree is unpacked last so that RPM_BUILD_DIR
# points to the right path, /usr/src/packages/BUILD/linux-%version
%setup -q -n linux-%{kversion}

# Determine which symbols to use for controlling the patch/file
# selection mechanism.
export PATCH_ARCH=%_target_cpu
chmod +x %_sourcedir/arch-symbols
SYMBOLS="$(%_sourcedir/arch-symbols)"
if [ -z "$SYMBOLS" ]; then
    echo "Unsupported architecture \`$PATCH_ARCH'" >&2
    exit 1
fi
if [ -e %_sourcedir/extra-symbols ]; then
    SYMBOLS="$SYMBOLS $(cat %_sourcedir/extra-symbols)"
fi
echo "Architecture symbol(s): $SYMBOLS"

# Write symbols to %_builddir/symbols so that other RPM sections
# can use the identical symbols. (Currently not needed!)
#echo $SYMBOLS > %_builddir/symbols

# Apply the patches needed for this architecture.
chmod +x %_sourcedir/guards
for patch in $(%_sourcedir/guards $SYMBOLS < %_sourcedir/series.conf); do
    if ! patch -s -E -p1 --no-backup-if-mismatch -i ../$patch; then
	echo "*** Patch $patch failed ***"
	exit 1
    fi
done

source %{SOURCE30}  # config_subst.sh

# Install all config files that make sense for that particular
# kernel.
configs="$(%_sourcedir/guards $SYMBOLS < %_sourcedir/config.conf)"
for config in $configs; do
    name=$(basename $config)
    path=arch/$(dirname $config)/defconfig.$name
    mkdir -p $(dirname $path)
    cat %_builddir/config/$config \
	| config_subst CONFIG_CFGNAME '"'$name'"' \
	| config_subst CONFIG_RELEASE %release \
	> $path
done

# For all architectures included, if there is a defconfig.default,
# make that the defconfig as well. If there is no defconfig.default,
# also remove the defconfig, as it is obviously not a tested, and
# woldn't work, anyway.
for config in $configs; do
    arch=$(dirname $config)
    if [ -e arch/$arch/defconfig.default ]; then
	cat arch/$arch/defconfig.default > arch/$arch/defconfig
    elif [ -e arch/$arch/defconfig.$PATCH_ARCH ]; then
	cat arch/$arch/defconfig.$PATCH_ARCH > arch/$arch/defconfig
    else
	rm -f arch/$arch/defconfig
    fi
done

chmod +x arch/ia64/scripts/toolchain-flags  # agruen: necessary?

%build
###################################################################
# Collect the filelist
find . -mindepth 1 -not -path ./linux.files > linux.files

chmod +x %{SOURCE31}  # merge-headers

# Create a custom hostname utility and place it in the path
# before the system wide one so that we don't need to create
# a temporary make file.
export PATH=%_builddir:$PATH
cat > %_builddir/hostname <<-EOF
	#! /bin/sh
	echo "%_arch.suse.de"
	EOF
chmod +x %_builddir/hostname

export ARCH=%_target_cpu
case $ARCH in
i?86)
    ARCH=i386 ;;
s390x)
    ARCH=s390 ;;
esac

if [ "$ARCH" != "$HOSTTYPE" ]; then
    MAKE_ARGS="ARCH=$ARCH"
%ifarch mips
    echo "CONFIG_CROSSCOMPILE=y" >> .config
%endif
fi

# Configure the kernel sources for each supported configuration

set +o posix  # turn on bash extensions
mkdir FLAVORS
for config in arch/$ARCH/defconfig.* ; do
    flavor=${config/*defconfig.}
    cfg="CONFIG_FLAVOR_$(echo $flavor | tr a-z A-Z)"
    ln -s ../$cfg FLAVORS/\"$flavor\"

    # UML needs a slightly different setup; we cannot support it
    # in the meta-configuration.
    [ $flavor = um ] && continue

    cp $config .config
    yes '' \
	| make %{?jobs:-j%jobs} oldconfig $MAKE_ARGS > /dev/null

    # Check for changes (and abort if there are any).
    differences="$(
	diff -U0 <(sort $config) <(sort .config) \
	| grep '^[-+][^-+]'
    )" || true
    if [ -n "$differences" ]; then
	echo "Configuration differences:"
	echo "$differences"
	if echo "$differences" | grep -q '^+' ; then
	    exit 1
	fi
    fi

    make include/linux/version.h $MAKE_ARGS
    mkdir $cfg
    sed -e '/^CONFIG_CFGNAME=/d' .config > $cfg/.config
    cp include/linux/version.h include/linux/autoconf.h $cfg/
    make -s %{?jobs:-j%jobs} distclean $MAKE_ARGS
done
set -o posix  # turn off bash extensions

# Merge the configurations

any_defined() {
    while [ $# -gt 1 ]; do
	echo -n "defined($1) || "
	shift
    done
    echo -n "defined($1)"
}

(   cat <<-EOF
	ifeq (\$(CONFIG_CFGNAME),)
	-include /var/adm/running-kernel.make
	endif
	EOF
	cd FLAVORS
	%{SOURCE31} --make CONFIG_CFGNAME */.config
) > .config
(   cat <<-EOF
	#if !($(any_defined CONFIG_FLAVOR_*))
	# include </var/adm/running-kernel.h>
	#endif
	EOF
    %{SOURCE31} CONFIG_FLAVOR_*/autoconf.h
) > include/linux/autoconf.h
(   cat <<-EOF
	#if !($(any_defined CONFIG_FLAVOR_*))
	# include </var/adm/running-kernel.h>
	#endif
	EOF
    %{SOURCE31} CONFIG_FLAVOR_*/version.h
) > include/linux/version.h

# Add files generated by configuring
any_flavor="$( cd FLAVORS ; set -- * ; echo $1 )"
make include/asm $MAKE_ARGS CONFIG_CFGNAME=\"$any_flavor\"
cat >> linux.files <<-EOF
	.config
	./include/linux/version.h
	./include/linux/autoconf.h
	./include/asm
	EOF

rm -r CONFIG_FLAVOR_* FLAVORS

%install
###################################################################
# Set up $RPM_BUILD_ROOT
rm -rf $RPM_BUILD_ROOT
mkdir -p $RPM_BUILD_ROOT/usr/src/linux-%ver_str
ln -sf linux-%ver_str $RPM_BUILD_ROOT/usr/src/linux
cpio -p $RPM_BUILD_ROOT/usr/src/linux-%ver_str < linux.files

## Install the documentation and demo modules
DOC=$RPM_BUILD_ROOT/usr/share/doc/packages/%name
mkdir -p $DOC
#cp %{SOURCE?} $DOC
#bzip2 -cd %{SOURCE21} | tar -xf - -C $DOC
#ln -s /usr/share/doc/packages/%name/README.SuSE \
#    $RPM_BUILD_ROOT/usr/src/linux/

# Generate a list of known flavors.
export ARCH=%_target_cpu
case $ARCH in
i?86)
    ARCH=i386 ;;
s390x)
    ARCH=s390 ;;
esac

shopt -s nullglob
flavors=
for config in arch/$ARCH/defconfig.* ; do
    flavor="${config/*defconfig.}"
    [ "$flavor" = um ] && continue
    flavors="$flavors $flavor"
done
flavors="${flavors:1}"
shopt -u nullglob

# The init script that adapts /var/adm/running-kernel.{h,make}.
mkdir -p $RPM_BUILD_ROOT/etc/rc.d
sed -e "s,@FLAVORS@,$flavors," %{SOURCE32} \
> $RPM_BUILD_ROOT/etc/rc.d/running-kernel

mkdir -p $RPM_BUILD_ROOT/var/adm
touch $RPM_BUILD_ROOT/var/adm/running-kernel.h \
      $RPM_BUILD_ROOT/var/adm/running-kernel.make

%post
#%{fillup_and_insserv -f running-kernel}  ## doesn't work: ???
/sbin/insserv running-kernel

if [ -e /.buildenv ]; then
    # Autobuild has a modified version of uname that reports a specific
    # kernel version if /.kernelversion exists.
    flavor="$(
	ARCH=%_target_cpu
	case $ARCH in
	(i?86)
	    ARCH=i386 ;;
	s390x)
	    ARCH=s390 ;;
	esac

	cd /usr/src/linux-%ver_str/arch/$ARCH
	set -- defconfig.*
	[ -e defconfig.default ] && set -- defconfig.default
	echo ${1/defconfig.}
    )"

    echo %ver_str-$flavor > /.kernelversion
fi

/etc/rc.d/running-kernel

%postun
%{insserv_cleanup}

%files
%defattr(-, root, root)
/usr/src/linux
/usr/src/linux-%ver_str
/usr/share/doc/packages/%name
%ghost /var/adm/running-kernel.h
%ghost /var/adm/running-kernel.make
%attr(755, root, root) /etc/rc.d/running-kernel
