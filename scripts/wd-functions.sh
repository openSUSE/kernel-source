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
scripts_dir=$(dirname "$0")

get_branch_name()
{
    if $using_cvs; then
        sed -ne 's:^T::p' "$scripts_dir"/../CVS/Tag 2>/dev/null || :
    else
        # FIXME: guess a branch name when a non-branch revision is checked
        # out
        local res=$(sed -ne 's|^ref: refs/heads/||p' "$scripts_dir"/../.git/HEAD 2>/dev/null)
        echo "$res"
    fi
}

if $using_git && test -z "$CHECKED_GIT_HOOKS"; then
    export CHECKED_GIT_HOOKS=1
    if ! "$scripts_dir"/install-git-hooks --check; then
        echo "WARNING: You should run $scripts_dir/install-git-hooks to enable pre-commit checks." >&2
    fi
    if ! git var GIT_COMMITTER_IDENT | grep -Eiq '@(suse\.(de|com|cz)|novell\.com)>'; then
        echo "WARNING: You should set your suse email address in git"  >&2
        echo "WARNING: E.g. by running 'git config --global user.email <your login>@suse.de'" >&2
    fi
fi

# vim: sw=4:sts=4:et
