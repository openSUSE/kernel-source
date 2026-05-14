#
# spec file for package kernel-syms
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


%define git_commit ece3f96068f9dd4e96094e07980a9a1c7987c4a9
%define variant %{nil}

%include %_sourcedir/kernel-spec-macros

Name:           kernel-syms
Version:        6.4.0
%if 0%{?is_kotd}
Release:        <RELEASE>.gece3f96
%else
Release:        0
%endif
Summary:        Kernel Symbol Versions (modversions)
License:        GPL-2.0-only
Group:          Development/Sources
URL:            https://www.kernel.org/
BuildRequires:  coreutils
ExclusiveArch:  aarch64 armv7hl ppc64le s390x x86_64
