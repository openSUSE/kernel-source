#############################################################################
# Copyright (c) 2008,2009 Novell, Inc.
# All Rights Reserved.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.   See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, contact Novell, Inc.
#
# To contact Novell about this file by physical or electronic mail,
# you may find current contact information at www.novell.com
#############################################################################

# to be sourced by scripts that need a GIT working directory

if git rev-parse HEAD >/dev/null 2>&1; then
    using_git=true
else
    using_git=false
    echo "WARNING: not in a GIT working directory, things might break." >&2
    echo >&2
fi
scripts_dir=$(dirname "$0")

get_branch_name()
{
    if $using_git; then
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
    suse_domains_re='(suse\.(de|com|cz)|novell\.com)'
    kerncvs_re='(kerncvs(\.suse\.de)?|10\.10\.1\.75)'
    if (echo $EMAIL; hostname -f) | grep -Eiq "aaa[@.]$suse_domains_re\\>" || \
        git config remote.origin.url | grep -Eiq "\\<$kerncvs_re:"; then
        # only warn when used in suse
        if ! git var GIT_COMMITTER_IDENT | grep -Eiq "@$suse_domains_re>"; then
            echo "WARNING: You should set your suse email address in git"  >&2
            echo "WARNING: E.g. by running 'git config --global user.email <your login>@suse.de'" >&2
        fi
    fi
fi

# vim: sw=4:sts=4:et
