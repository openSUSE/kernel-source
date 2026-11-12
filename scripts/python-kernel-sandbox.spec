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
Name:           python-kernel-sandbox
Version:        0
Release:        0
Summary:        A CLI that takes a kernel-source commit and gets you a booted QEMU VM running that kernel
License:        GPL-2.0-only
URL:            https://github.com/hramrach/kernel-source/tree/scripts
BuildRequires:  %{python_module PyYAML}
# certifi is needed by pygit2
BuildRequires:  %{python_module certifi}
BuildRequires:  %{python_module flit-core >= 3.11}
BuildRequires:  %{python_module pip}
BuildRequires:  %{python_module pygit2}
BuildRequires:  %{python_module pytest}
BuildRequires:  fdupes
BuildRequires:  python-rpm-macros
Requires:       python-PyYAML
# certifi is needed by pygit2
Requires:       python-certifi
Requires:       python-pygit2
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
( cd %{_sourcedir}/kernel-sandbox ; tar -cf - .;) | tar -xvf-
cat >> pyproject.toml <<END
[build-system]
requires = ['flit_core >=3.11,<5']
build-backend = 'flit_core.buildapi'

[project]
name = 'kernel-sandbox'
description = '%{summary}'
version = '%{version}'
license = '%license'
readme = 'README-execute.md'
authors = [{name = 'SUSE Kernel maintainers', email = 'kernel@suse.de'}]
requires-python = '>=3.6'

[project.urls]
source = 'https://github.com/openSUSE/kernel-source/tree/scripts/scripts'

[project.scripts]
kernel-sandbox = 'kernel_sandbox.kernel_sandbox:main'

END

%build
%pyproject_wheel

%install
%pyproject_install
%python_clone -a %{buildroot}%{_bindir}/kernel-sandbox
%fdupes %{buildroot}%{python3_sitelib}

%check
%pytest

%if %{without libalternatives}
%post
%python_install_alternative kernel-sandbox

%postun
%python_uninstall_alternative kernel-sandbox
%endif

%files %{python_files}
%doc README.md README-execute.md
%python_alternative %{_bindir}/kernel-sandbox
%{python_sitelib}/kernel_sandbox
%{python_sitelib}/kernel_sandbox-%{version}*-info

%changelog
