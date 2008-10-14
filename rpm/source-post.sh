relink() {
    if [ -h "$2" ]; then
	local old=$(readlink "$2")
	[ "$old" = "$1" ] && return 0
	echo "Changing symlink $2 from $old to $1"
    elif [ -e "$2" ]; then
	echo "Replacing file $2 with symlink to $1"
    fi
    rm -f "$2" \
    && ln -s "$1" "$2"
}

relink linux-@KERNELRELEASE@@VARIANT@ /usr/src/linux@VARIANT@
relink linux-@KERNELRELEASE@@VARIANT@-obj /usr/src/linux@VARIANT@-obj
