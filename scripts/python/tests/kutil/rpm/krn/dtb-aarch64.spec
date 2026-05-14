#
# spec file for package dtb-aarch64
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


%define srcversion 6.4
%define patchversion 6.4.0
%define variant %{nil}

%include %_sourcedir/kernel-spec-macros

%(chmod +x %_sourcedir/{guards,apply-patches,check-for-config-changes,group-source-files.pl,split-modules,modversions,kabi.pl,arch-symbols,check-module-license,splitflist,mergedep,moddep,modflist,kernel-subpackage-build})

Name:           dtb-aarch64
Version:        6.4.0
%if 0%{?is_kotd}
Release:        <RELEASE>.gece3f96
%else
Release:        0
%endif
Summary:        Device Tree files for $MACHINES
License:        GPL-2.0-only
Group:          System/Boot
URL:            https://www.kernel.org/
BuildRequires:  cpp
BuildRequires:  dtc >= 1.4.3
BuildRequires:  xz
ExclusiveArch:  aarch64
