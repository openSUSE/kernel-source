echo Setting up /lib/modules/%ver_str
/sbin/depmod -a -F /boot/System.map-%ver_str %ver_str

initrd=initrd
if [ -f /boot/vmlinuz-%ver_str ]; then
    image=vmlinuz
elif [ -f /boot/image-%ver_str ]; then
    image=image
elif [ -f /boot/vmlinux-%ver_str ]; then
    image=vmlinux
elif [ -f /boot/linux-%ver_str ]; then
    # This is User Mode Linux; it may be installed on the same
    # root filesystem as a native kernel. Make sure we don't mess
    # up the native kernel's symlinks!
    image=um-linux
    initrd=um-initrd
    run_mkinitrd=
fi

# Update the /boot/vmlinuz and /boot/initrd symlinks
for x in /boot/$image /boot/$initrd; do
    if [ -e $x -a "$(readlink $x)" != ${x##*/}-%ver_str ]; then
	mv -f $x $x.previous
    fi
    rm -f $x
    ln -s ${x##*/}-%ver_str $x
done

if [ "$YAST_IS_RUNNING" != instsys -a -n "$run_mkinitrd" ]; then
    if [ -f /etc/fstab ]; then
	if ! /sbin/mkinitrd -k /boot/$image-%ver_str \
			    -i /boot/$initrd-%ver_str; then
	    echo "/sbin/mkinitrd failed" >&2
	    exit 1
	fi
    else
	echo "please run mkinitrd as soon as your system is complete"
    fi

    if [ -x /sbin/new-kernel-pkg ]; then
	# Notify boot loader that a new kernel image has been installed.
	# (during initial installation the boot loader configuration does not
	#  yet exist when the kernel is installed, but yast kicks the boot
	#  loader itself later.)
	/sbin/new-kernel-pkg %ver_str
    fi
fi
