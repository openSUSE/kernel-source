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


%define git_commit 513d2ec25a33ba4bd970269abb48e060007939b7
%define variant %{nil}

%include %_sourcedir/kernel-spec-macros

Name:           kernel-syms
Version:        6.17.1
%if 0%{?is_kotd}
Release:        <RELEASE>.g513d2ec
%else
Release:        0
%endif
Summary:        Kernel Symbol Versions (modversions)
License:        GPL-2.0-only
Group:          Development/Sources
URL:            https://www.kernel.org/
BuildRequires:  coreutils
ExclusiveArch:  %ix86 aarch64 armv6hl armv7hl ppc64le riscv64 s390x x86_64
