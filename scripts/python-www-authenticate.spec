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
Name:           python-www-authenticate
Version:        0.9.2
Release:        0
Summary:        Parser for WWW-Authenticate headers
License:        BSD-3-Clause-Attribution
URL:            https://github.com/alexsdutton/www-authenticate
BuildRequires:  %{python_module flit-core >= 3.11}
BuildRequires:  %{python_module pip}
BuildRequires:  %{python_module pytest}
BuildRequires:  fdupes
BuildRequires:  python-rpm-macros
BuildArch:      noarch
%python_subpackages

%description

%prep
( cd %{_sourcedir}/python ; tar -cf - www_authenticate tests/*www_authenticate* ;) | tar -xvf-
cat >> pyproject.toml <<END
[build-system]
requires = ['flit_core >=3.11,<5']
build-backend = 'flit_core.buildapi'

[project]
name = 'www-authenticate'
description = '%{summary}'
version = '%{version}'
license = '%license'
readme = 'www_authenticate/README.rst'
authors = [{name = 'Alexander Dutton', email = 'www-authenticate-lib@alexdutton.co.uk'}]
requires-python = '>=3.4'

[project.urls]
source = 'https://github.com/hramrach/kernel-source/tree/scripts'

END

%build
%pyproject_wheel

%install
%pyproject_install
%fdupes %{buildroot}%{python3_sitelib}

%check
%pytest

%files %{python_files}
%doc www_authenticate/README.rst
%license www_authenticate/LICENSE
%{python_sitelib}/www_authenticate
%{python_sitelib}/www_authenticate-%{version}*-info

%changelog
