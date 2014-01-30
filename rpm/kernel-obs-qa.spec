#
# spec file for package kernel-obs-qa
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


Name:           kernel-obs-qa
BuildRequires:  kernel-default
BuildRequires:  module-init-tools
%ifarch %ix86 x86_64
BuildRequires:  kernel-xen
%endif
%if 0%{?suse_version} < 1200
# for SLE 11
BuildRoot:      %{_tmppath}/%{name}-%{version}-build
%endif
Summary:        Basic QA tests for the kernel
License:        GPL-2.0
Group:          SLES
Version:        1
Release:        0

%description
This package is using the kernel compiled within Open Build Service(OBS)
projects and runs basic tests.

%prep

%build

%check
# More tests are comming, currently the main test is the existens of
# this spec file. It does trigger a build within OBS VM which is using
# the kernel of the same project.

# test suites should be packaged in other packages, but build required
# and called here.

/sbin/modprobe loop || exit 1

%install
mkdir -p %{buildroot}/usr/share/kernel-qa/
touch %{buildroot}/usr/share/kernel-qa/logfile

%files
%defattr(-,root,root)
/usr/share/kernel-qa

%changelog
