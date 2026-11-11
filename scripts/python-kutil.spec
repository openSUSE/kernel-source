#
# spec file for package python-kutil
#
# Copyright (c) 2026 SUSE LLC
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An 'Open Source License' is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via https://bugs.opensuse.org/
#

%{?sle15_python_module_pythons}
Name:           python-kutil
Version:        0
Release:        0
Summary:        Utility libraries for working with SUSE kernel sources
License:        GPL-2.0-only
URL:            https://github.com/hramrach/kernel-source/tree/scripts
BuildRequires:  %{python_module flit-core >= 3.11}
BuildRequires:  %{python_module pip}
BuildRequires:  %{python_module pytest}
BuildRequires:  fdupes
BuildRequires:  python3
BuildRequires:  python-rpm-macros
BuildArch:      noarch
%python_subpackages

%description

%prep
( cd %{_sourcedir} ; tar -cf - python/kutil guards compute-PATCHVERSION python/tests/*kutil* ;) | tar -xvf-
./compute-PATCHVERSION --help
cd python
cat >> pyproject.toml <<END
[build-system]
requires = ['flit_core >=3.11,<5']
build-backend = 'flit_core.buildapi'

[project]
name = 'kutil'
description = '%{summary}'
version = '%{version}'
license = '%license'
authors = [{name = 'SUSE Kernel maintainers', email = 'kernel@suse.de'}]
requires-python = '>=3.4'

[project.urls]
source = 'https://github.com/hramrach/kernel-source/tree/scripts'

END

%build
cd python
%pyproject_wheel

%install
cd python
%pyproject_install
%fdupes %{buildroot}%{python3_sitelib}

%check
cd python
%pytest

%files %{python_files}
%{python_sitelib}/kutil
%{python_sitelib}/kutil-%{version}*-info

%changelog
