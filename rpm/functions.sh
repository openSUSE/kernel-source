# Readlink is not present on some older distributions: emulate it.
readlink() {
    local path=$1 ll

    if [ -L "$path" ]; then
	ll="$(LC_ALL=C ls -l "$path" 2> /dev/null)" &&
	echo "${ll/* -> }"
    else
	return 1
    fi
}
relink() {
    if [ -h "$2" ]; then
	echo "Changing symlink $2 from $(readlink "$2") to $1"
    elif [ -e "$2" ]; then
	echo "Replacing file $2 with symlink to $1"
    fi
    rm -f "$2" \
    && ln -s "$1" "$2"
}
