#
# spec file for package kernel-dummy (Version 0.0)
#
# Copyright (c) 2003 SuSE Linux AG, Nuernberg, Germany.
# This file and all modifications and additions to the pristine
# package are under the same license as the package itself.
#
# Please submit bugfixes or comments via http://www.suse.de/feedback/
#

# norootforbuild
# neededforbuild

Name:         kernel-dummy
License:      GPL
Provides:     linux
Autoreqprov:  off
Summary:      Dummy summary
Group:        Development/Sources
Version:      0.0
Release:      0
BuildRoot:    %_tmppath/%name-%version-build

%description
Dummy description.

%install
rm -rf %buildroot
mkdir -p %buildroot/etc
echo dummy > %buildroot/etc/dummy

%files
%defattr(-, root, root)
/etc/dummy
