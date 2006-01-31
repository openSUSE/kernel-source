# norootforbuild

BuildRequires: kernel-source kernel-syms

Name:         novell-kmp
License:      GPL
Group:        System/Kernel
Summary:      Example Kernel Module Package
Version:      1.1
Release:      0
Source0:      novell-kmp-%version.tar.bz2
BuildRoot:    %{_tmppath}/%{name}-%{version}-build

%suse_kernel_module_package kdump um
%define arch %(echo %_target_cpu | sed -e 's/i.86/i386/')

%description
This is an example Kernel Module Package.

%package KMP
Summary: Example Kernel Module
Group: System/Kernel

%description KMP
This is one of the sub-packages for a specific kernel. All the
sub-packages will share the same summary, group, and description.

%prep
%setup -n novell-kmp-%version
set -- *
mkdir source
mv "$@" source/
mkdir obj

%build
export EXTRA_CFLAGS='-DVERSION=\"%version\"'
for flavor in %flavors_to_build; do
    rm -rf obj/$flavor
    cp -r source obj/$flavor
    make -C /usr/src/linux-obj/%arch/$flavor modules \
	M=$PWD/obj/$flavor
done

%install
export INSTALL_MOD_PATH=$RPM_BUILD_ROOT
export INSTALL_MOD_DIR=updates
for flavor in %flavors_to_build; do
    make -C /usr/src/linux-obj/%arch/$flavor modules_install \
	 M=$PWD/obj/$flavor
done

%changelog
* Sat Jan 28 2006 - agruen@suse.de
- Initial package.
