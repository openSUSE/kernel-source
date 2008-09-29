relink linux-@KERNELRELEASE@@VARIANT@ /usr/src/linux@VARIANT@
relink linux-@KERNELRELEASE@-obj /usr/src/linux-obj

if [ -e /.buildenv ]; then
    # Autobuild has a modified version of uname that reports a specific
    # kernel version if /.kernelversion exists.
    arch=$(echo %_target_cpu \
    	   | sed -e s/i.86/i386/  -e s/sun4u/sparc64/ \
    		 -e s/arm.*/arm/  -e s/sa110/arm/ \
		 -e s/s390x/s390/ -e s/parisc64/parisc/ \
		 -e s/ppc.*/powerpc/)
    flavor="$(
	cd /usr/src/linux-@KERNELRELEASE@/arch/$arch
	set -- defconfig.*
	[ -e defconfig.default ] && set -- defconfig.default
	echo ${1/defconfig.}
    )"

    echo @KERNELRELEASE@-$flavor > /.kernelversion
fi
