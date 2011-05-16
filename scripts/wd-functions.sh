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

_find_tarball()
{
    local version=$1 dir

    for dir in . /mounts/mirror/kernel/v2.6{,/testing} ${MIRROR}; do
        if test -r "$dir/linux-$version.tar.bz2"; then
            echo "$dir/linux-$version.tar.bz2"
            return
        fi
    done
}

_get_tarball_from_git()
{
    local version=$1 tag url

    git=${LINUX_GIT:-$HOME/linux-2.6}
    if test ! -d "$git/.git"; then
        echo "No linux-2.6 git tree found (try setting the LINUX_GIT variable)" >&2
        exit 1
    fi
    case "$version" in
    *next-*)
        tag=refs/tags/next-${version##*next-}
        url=git://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git
        ;;
    2.6.*-*-g???????)
        tag="v$version"
        url=git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux-2.6.git
        ;;
    *)
        tag=refs/tags/"v$version"
        url=git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux-2.6.git
    esac
    if ! git --git-dir="$git/.git" cat-file -e "$tag" 2>/dev/null; then
        case "$tag" in
        refs/tags/*)
            git --git-dir="$git/.git" fetch "$url" "$tag:$tag"
            ;;
        *)
            # v2.6.X.Y-rcZ-gabcdef1, not a real tag
            git --git-dir="$git/.git" fetch --tags "$url" \
                refs/heads/master:refs/tags/latest
        esac
    fi
    git --git-dir="$git/.git" archive --prefix="linux-$version/" "$tag"
}

get_tarball()
{
    local version=$1 dest=$2 tarball

    tarball=$(_find_tarball "$version")
    if test -n "$tarball"; then
        cp "$tarball" "$dest/linux-$version.tar.bz2.part" || exit
        mv "$dest/linux-$version.tar.bz2.part" "$dest/linux-$version.tar.bz2"
        return
    fi
    echo "Warning: could not find linux-$version.tar.bz2, trying to create it from git" >&2
    set -o pipefail
    _get_tarball_from_git "$version" | bzip2 -9 \
        >"$dest/linux-$version.tar.bz2.part"
    if test $? -ne 0; then
        exit 1
    fi
    mv "$dest/linux-$version.tar.bz2.part" "$dest/linux-$version.tar.bz2"
    set +o pipefail
}

unpack_tarball()
{
    local version=$1 dest=$2 tarball

    tarball=$(_find_tarball "$version")
    mkdir -p "$dest"
    if test -n "$tarball"; then
        echo "Extracting $tarball"
        tar -xjf "$tarball" -C "$dest" --strip-components=1
        return
    fi
    echo "Warning: could not find linux-$version.tar.bz2, trying to create it from git" >&2
    echo "alternatively you can put an unpatched kernel tree to $dest" >&2
    set -o pipefail
    _get_tarball_from_git "$version" | tar -xf - -C "$dest" --strip-components=1
    if test $? -ne 0; then
        rm -rf "$dest"
        exit 1
    fi
    set +o pipefail
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
