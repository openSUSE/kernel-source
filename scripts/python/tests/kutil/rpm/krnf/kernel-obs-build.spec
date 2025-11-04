#
# spec file for package kernel-obs-build
#
# Copyright (c) 2025 SUSE LLC
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via https://bugs.opensuse.org/
#
# needsrootforbuild


#!BuildIgnore: post-build-checks

%define patchversion 6.17.1
%define variant %{nil}

%include %_sourcedir/kernel-spec-macros

%if 0%{?suse_version}
%if "%{nil}"
%global kernel_flavor %{nil}
%else
%ifarch %ix86
%global kernel_flavor -pae
%else
%ifarch armv7l armv7hl
%global kernel_flavor -lpae
%else
%global kernel_flavor -default
%endif
%endif
%endif
%global kernel_package kernel%kernel_flavor-srchash-513d2ec25a33ba4bd970269abb48e060007939b7
%endif
%if 0%{?rhel_version}
%global kernel_package kernel
%endif

Name:           kernel-obs-build
Version:        6.17.1
%if 0%{?is_kotd}
Release:        <RELEASE>.g513d2ec
%else
Release:        0
%endif
Summary:        package kernel and initrd for OBS VM builds
License:        GPL-2.0-only
Group:          SLES
Provides:       kernel-obs-build-srchash-513d2ec25a33ba4bd970269abb48e060007939b7
BuildRequires:  coreutils
BuildRequires:  device-mapper
BuildRequires:  dracut
BuildRequires:  %kernel_package
BuildRequires:  util-linux
%if 0%{?suse_version} > 1550 || 0%{?sle_version} > 150200
BuildRequires:  zstd
%endif
ExclusiveArch:  aarch64 armv6hl armv7hl ppc64le riscv64 s390x x86_64
