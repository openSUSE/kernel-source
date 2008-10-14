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
