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
cd /usr/src
for a in linux-@KERNELRELEASE@@VARIANT@-obj/*; do
    if [ ! -d "$a" -o -h "$a" ]; then
        # skip symlinks like i586 -> i386
        continue
    fi
    for d in "$a"/*; do
        arch_flavor=${d#*/}
        relink ../../"$d" /usr/src/linux-obj/"$arch_flavor"
    done
done
