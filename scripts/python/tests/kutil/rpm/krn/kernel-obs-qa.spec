#
# spec file for package kernel-obs-qa
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


%define patchversion 6.4.0
%define variant %{nil}

%include %_sourcedir/kernel-spec-macros

Name:           kernel-obs-qa
Version:        6.4.0
%if 0%{?is_kotd}
Release:        <RELEASE>.gece3f96
%else
Release:        0
%endif
Summary:        Basic QA tests for the kernel
License:        GPL-2.0-only
Group:          SLES
BuildRequires:  kernel-default
# kernel-obs-build must be also configured as VMinstall, but is required
# here as well to avoid that qa and build package build parallel
%if ! 0%{?qemu_user_space_build}
BuildRequires:  kernel-obs-build-srchash-ece3f96068f9dd4e96094e07980a9a1c7987c4a9
%endif
BuildRequires:  modutils
ExclusiveArch:  aarch64 armv7hl ppc64le s390x x86_64
