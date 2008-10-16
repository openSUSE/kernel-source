# to be sourced by scripts that need a GIT / CVS working directory

if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && `git rev-parse --is-inside-work-tree`; then
    scm=GIT
    using_git=true
    using_cvs=false
elif test -d CVS; then
    scm=CVS
    using_cvs=true
    using_git=false
else
    echo "Error: not in CVS / GIT working directory" >&2
    exit 1
fi

# vim: sw=4:ts=4:et
