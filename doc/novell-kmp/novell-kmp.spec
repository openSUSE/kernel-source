BuildRequires: kernel-source kernel-syms

Name:         novell-kmp
License:      GPL
Group:        System/Kernel
Summary:      Kernel module package example
Version:      1.1
Release:      0
Source0:      novell-kmp-%version.tar.bz2
BuildRoot:    %{_tmppath}/%{name}-%{version}-build

%suse_kernel_module_package -v 13 -r 98 kdump uml
%define arch %(echo %_target_cpu | sed -e 's/i.86/i386/')

%description
An example kernel module package

%prep
%setup -n novell-kmp-%version
mkdir source
mv * source/ || :
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
* Thu Jan 27 2006 - agruen@suse.de
- Initial package.
