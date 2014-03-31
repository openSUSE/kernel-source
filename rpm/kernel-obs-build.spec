#
# spec file for package kernel-obs-build
#
# Copyright (c) 2014 SUSE LINUX Products GmbH, Nuernberg, Germany.
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via http://bugs.opensuse.org/
#
# needsrootforbuild


#!BuildIgnore: post-build-checks

Name:           kernel-obs-build
BuildRequires:  coreutils
BuildRequires:  device-mapper
BuildRequires:  mkinitrd
BuildRequires:  util-linux

BuildRequires:  kernel-default
%ifarch %ix86 x86_64
BuildRequires:  kernel-xen
%endif
%if 0%{?suse_version} < 1200
# For SLE 11
BuildRequires:  yast2-bootloader
BuildRoot:      %{_tmppath}/%{name}-%{version}-build
%endif
Summary:        package kernel and initrd for OBS VM builds
License:        GPL-2.0
Group:          SLES
Version:        1
Release:        0

%description
This package is repackaging already compiled kernels to make them usable
inside of Open Build Service (OBS) VM builds. An initrd with some basic
kernel modules is generated as well, but further kernel modules can be 
loaded during build when installing the kernel package.

%prep

%build
# a longer list to have them also available for qemu cross builds where x86_64 kernel runs in eg. arm env.
# this list of modules where available on build workers of build.opensuse.org, so we stay compatible.
export KERNEL_MODULES="loop dm-mod dm-snapshot binfmt-misc fuse kqemu squashfs ext2 ext3 ext4 reiserfs nf_conntrack_ipv6 binfmt_misc virtio_pci virtio_blk fat vfat nls_cp437 nls_iso8859-1 ibmvscsi"
ROOT=""
[ -e "/dev/vda" ] && ROOT="-d /dev/vda"
[ -e /dev/hda1 ] && ROOT="-d /dev/hda1" # for xen builds
%define kernel_name vmlinu?
%ifarch s390 s390x
%define kernel_name image
%endif
ls /boot
/sbin/mkinitrd $ROOT \
               -m "$KERNEL_MODULES" \
               -k /boot/%{kernel_name}-*-default -M /boot/System.map-*-default -i /tmp/initrd.kvm -B

%ifarch %ix86 x86_64
/sbin/mkinitrd $ROOT \
               -m "$KERNEL_MODULES" \
               -k /boot/vmlinuz-xen -M /boot/System.map-*-xen -i /tmp/initrd.xen
%endif

%install
install -d -m 0755 $RPM_BUILD_ROOT
cp -v /boot/%{kernel_name}-*-default $RPM_BUILD_ROOT/.build.kernel.kvm
cp -v /tmp/initrd.kvm $RPM_BUILD_ROOT/.build.initrd.kvm
%ifarch %ix86 x86_64
cp -v /boot/vmlinuz-*-xen $RPM_BUILD_ROOT/.build.kernel.xen
cp -v /tmp/initrd.xen $RPM_BUILD_ROOT/.build.initrd.xen
%endif

%files
%defattr(-,root,root)
/.build.kernel.*
/.build.initrd.*

%changelog
