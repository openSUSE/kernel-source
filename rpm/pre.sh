# see bug #259303
# this script runs when the kernel gets updated with YaST
# YaST calls rpm always with -U
# -U replaces all packages with the new one
# rpm removes the files from the old packages after the postinstall script ran
# this will double the required space below /boot
# remove the files from the old packages to make room for the new initrd
# rpm may complain about low disk space if /boot/vmlinux does not fit
if [ @BASE_PACKAGE@ = 1 -a "$YAST_IS_RUNNING" != "" ]; then
	mydf="$( POSIXLY_CORRECT=1 df -P /boot/ | awk '/^(\/|-[[:blank:]])/{ print $4}' )"
	if test "$mydf" != "" ; then
		echo "Free diskspace below /boot: $mydf blocks"
		# echo "512 byte blocks: $(( 2 * 1024 * 20 ))"
		if test "$mydf" -lt  "40960" ; then
			echo "make room for new kernel '@FLAVOR@' because there are less than 20MB available."
			# disabled because it breaks patch rpms
			#rm -fv /boot/@IMAGE@-*-@FLAVOR@
			rm -fv /boot/initrd-*-@FLAVOR@
		fi
	fi
fi


# On AArch64 we switched from 64k PAGE_SIZE to 4k PAGE_SIZE. Unfortunately
# btrfs can only use file systems created with the same PAGE_SIZE. So we
# check if the user has any btrfs file systems mounted and refuse to install
# in that case.
if [ $( uname -m ) = aarch64 -a \
     "$( zgrep CONFIG_ARM64_64K_PAGES=y /proc/config.gz )" -a \
     @FLAVOR@ = default ]; then
	if [ "$FORCE_4K" = 1 ]; then
		# The user knows what he's doing, let him be.
		exit 0
	fi

	if [ "$YAST_IS_RUNNING" = "instsys" ]; then
		# We're probably test installing the kernel, that should succeed
		exit 0
	fi

	cat >&2 <<-EOF

		You are running on a 64kb PAGE_SIZE kernel. The default kernel
		switched to 4kb PAGE_SIZE which will prevent it from mounting btrfs
		or the swap partition.
		
		To ensure that your system still works, I am refusing to install
		this kernel. If you want to force installation regardlesss, reinstall
		with the environment variable FORCE_4K set to 1.

		To stay with a 64kb PAGE_SIZE kernel, please follow these steps:

		        $ zypper in kernel-64kb
		        [ reboot into the new kernel ]
		        $ zypper rm kernel-default

		You will then be on the 64kb PAGE_SIZE kernel and can update your
		system normally.
	EOF

	exit 1
fi
