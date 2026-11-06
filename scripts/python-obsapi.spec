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

%if 0%{?suse_version} > 1500
%bcond_without libalternatives
%else
%bcond_with libalternatives
%endif
%{?sle15_python_module_pythons}
Name:           python-obsapi
Version:        0
Release:        0
Summary:        Utility libraries for talking to OBS and Gitea API
License:        GPL-2.0-only
URL:            https://github.com/hramrach/kernel-source/tree/scripts
BuildRequires:  %{python_module PyYAML}
BuildRequires:  %{python_module certifi}
BuildRequires:  %{python_module flit-core >= 3.11}
BuildRequires:  %{python_module kutil}
BuildRequires:  %{python_module pip}
BuildRequires:  %{python_module pytest}
BuildRequires:  %{python_module www-authenticate}
BuildRequires:  fdupes
BuildRequires:  git-core
BuildRequires:  openssh-common
BuildRequires:  python-rpm-macros
Requires:       git-core
Requires:       openssh-common
Requires:       python-PyYAML
Requires:       python-certifi
Requires:       python-kutil
Requires:       python-www-authenticate
BuildArch:      noarch
%if %{with libalternatives}
BuildRequires:  alts
Requires:       alts
%else
Requires(post): update-alternatives
Requires(postun): update-alternatives
%endif
%python_subpackages

%description

%prep
( cd %{_sourcedir}/python ; tar -cf - obsapi tests/*api* tests/kutil ;) | tar -xvf-
cat >> pyproject.toml <<END
[build-system]
requires = ['flit_core >=3.11,<5']
build-backend = 'flit_core.buildapi'

[project]
name = 'obsapi'
description = '%{summary}'
version = '%{version}'
license = '%license'
authors = [{name = 'SUSE Kernel maintainers', email = 'kernel@suse.de'}]
requires-python = '>=3.4'

[project.urls]
source = 'https://github.com/hramrach/kernel-source/tree/scripts'

[project.scripts]
bs-upload-kernel = 'obsapi.uploader:main'

END

%build
%pyproject_wheel

%install
%pyproject_install
%python_clone -a %{buildroot}%{_bindir}/bs-upload-kernel
%fdupes %{buildroot}%{python3_sitelib}

%check
%pytest -k api

%if %{without libalternatives}

%post
%python_install_alternative bs-upload-kernel

%postun
%python_uninstall_alternative bs-upload-kernel

%endif

%files %{python_files}
%python_alternative %{_bindir}/bs-upload-kernel
%{python_sitelib}/obsapi
%{python_sitelib}/obsapi-%{version}*-info

%changelog
