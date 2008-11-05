# to be sourced by scripts that need a GIT / CVS working directory

if test -d CVS; then
    scm=CVS
    using_cvs=true
    using_git=false
elif git rev-parse HEAD >/dev/null 2>&1; then
    scm=GIT
    using_git=true
    using_cvs=false
else
    echo "Error: not in CVS / GIT working directory" >&2
    exit 1
fi

if $using_git && test -z "$COMPLAINED_ABOUT_GIT_HOOKS" && ! ${0%/*}/install-git-hooks --check; then
    echo "WARNING: You should run ${0%/*}/install-git-hooks to enable pre-commit checks." >&2
    export COMPLAINED_ABOUT_GIT_HOOKS=true
fi

# vim: sw=4:ts=4:et
