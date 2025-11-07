#
# spec file for package kernel-vanilla
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
# needssslcertforbuild


%define srcversion 6.17
%define patchversion 6.17.1
%define git_commit 513d2ec25a33ba4bd970269abb48e060007939b7
%define variant %{nil}
%define compress_modules zstd
%define compress_vmlinux xz
%define livepatch livepatch%{nil}
%define livepatch_rt %{nil}
%define sb_efi_only 0
%define split_base 0
%define split_optional 0
%define supported_modules_check 0
%define build_flavor vanilla
%define generate_compile_commands 1
%define use_suse_kabi_tools 0
%define gcc_package gcc
%define gcc_compiler gcc

%include %_sourcedir/kernel-spec-macros

%(chmod +x %_sourcedir/{guards,apply-patches,check-for-config-changes,group-source-files.pl,split-modules,modversions,kabi.pl,arch-symbols,check-module-license,splitflist,mergedep,moddep,modflist,kernel-subpackage-build})

Name:           kernel-vanilla
Version:        6.17.1
%if 0%{?is_kotd}
Release:        <RELEASE>.g513d2ec
%else
Release:        0
%endif
Summary:        The Standard Kernel - without any SUSE patches
License:        GPL-2.0-only
Group:          System/Kernel
URL:            https://www.kernel.org/
%if 0%{?suse_version} > 1500 || 0%{?sle_version} > 150300
BuildRequires:  bash-sh
%endif
BuildRequires:  bc
BuildRequires:  bison
BuildRequires:  coreutils
BuildRequires:  fdupes
BuildRequires:  flex
# Cannot test %%CONFIG_GCC_PLUGINS here because the buildservice parser
# does not expand %%(...)
%if "%build_flavor" == "syzkaller"
# Needed by scripts/gcc-plugin.sh
BuildRequires:  %gcc_package-c++
BuildRequires:  %gcc_package-devel
%endif
BuildRequires:  hmaccalc
BuildRequires:  libopenssl-devel
BuildRequires:  modutils
BuildRequires:  python3-base
# Used to sign the kernel in the buildservice
BuildRequires:  openssl
BuildRequires:  pesign-obs-integration
%if 0%{?suse_version} > 1500 || 0%{?sle_version} >= 150300
# pahole for CONFIG_DEBUG_INFO_BTF
BuildRequires:  dwarves >= 1.22
%endif
BuildRequires:  %gcc_package
# for objtool
BuildRequires:  libelf-devel
# required for 50-check-kernel-build-id rpm check
BuildRequires:  elfutils
%ifarch %arm
BuildRequires:  u-boot-tools
%endif
%if %use_suse_kabi_tools
BuildRequires:  suse-kabi-tools
%endif
# Do not install p-b and dracut for the install check, the %post script is
# able to handle this
#!BuildIgnore: perl-Bootloader dracut distribution-release suse-kernel-rpm-scriptlets
# Remove some packages that are installed automatically by the build system,
# but are not needed to build the kernel
#!BuildIgnore: autoconf automake gettext-runtime libtool cvs gettext-tools udev insserv
ExclusiveArch:  aarch64 armv6hl armv7hl %ix86 ppc64le riscv64 s390x x86_64
