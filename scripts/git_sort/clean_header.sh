#!/bin/bash -e

# Filter a patch file such that it is properly formatted per SUSE rules.
# Useful when importing patches into SUSE's kernel-source.git.


progname=$(basename "$0")
libdir=$(dirname "$(readlink -f "$0")")
git_dir=$("$libdir"/../linux_git.sh) || exit 1

export GIT_DIR=$git_dir
: ${EDITOR:=${VISUAL:=vi}}

. "$libdir"/lib_from.sh
. "$libdir"/lib_tag.sh
. "$libdir"/lib.sh

usage () {
	echo "Usage: $progname [options] [patch file]"
	echo ""
	echo "Options:"
	echo "    -c, --commit=<refspec>      Upstream commit id used to tag the patch file."
	echo "    -r, --reference=<bsc>       bsc or fate number used to tag the patch file."
	echo "    -R, --soft-reference=<bsc>  bsc or fate number used to tag the patch file"
	echo "                                if no other reference is found."
	echo "    -s, --skip=<domain>         Skip adding Acked-by tag if there is already an"
	echo "                                attribution line with an email from this domain."
	echo "                                (Can be used multiple times.)"
	echo "    -h, --help                  Print this help"
	echo ""
}


result=$(getopt -o c:r:R:s:h --long commit:,reference:,soft-reference:,skip:,help -n "$progname" -- "$@")
if [ $? != 0 ]; then
	echo "Error: getopt error" >&2
	exit 1
fi

eval set -- "$result"

while true ; do
        case "$1" in
                -c|--commit)
					opt_commit=$2
					shift
					;;
                -r|--reference)
					opt_ref=$2
					shift
					;;
                -R|--soft-reference)
					opt_soft=$2
					shift
					;;
                -s|--skip)
					opt_skip+=($2)
					shift
					;;
                -h|--help)
					usage
					exit 0
					;;
                --)
					shift
					break
					;;
                *)
					echo "Error: could not parse arguments" >&2
					exit 1
					;;
        esac
	shift
done

# bash strips trailing newlines in variables, protect them with "---"
if [ -n "$1" ]; then
	filename=$1
	patch=$(cat "$filename" && echo ---)
	shift
else
	patch=$(cat && echo ---)
fi

if [ -n "$1" ]; then
	echo "Error: too many arguments" > /dev/stderr
	usage > /dev/stderr
	exit 1
fi

if echo -n "${patch%---}" | grep -q $'\r'; then
	patch=$(echo -n "${patch%---}" | sed -e 's/\r//g' && echo ---)
fi

body=$(echo -n "${patch%---}" | awk -f "$libdir"/patch_body.awk && echo ---)
# * Remove "From" line with tag, since it points to a local commit from
#   kernel.git that I created
# * Remove "Conflicts" section
header=$(echo -n "${patch%---}" | awk -f "$libdir"/patch_header.awk | from_extract | awk -f "$libdir"/clean_conflicts.awk && echo ---)


# Git-commit:

cherry=$(echo "$header" | tag_get "cherry picked from commit")
if [ "$cherry" ]; then
	if ! cherry=$(echo "$cherry" | expand_git_ref); then
		exit 1
	fi
	header=$(echo -n "$header" | tag_remove "cherry picked from commit")
fi

git_commit=$(echo "$header" | tag_get git-commit)
if [ "$git_commit" ]; then
	if ! git_commit=$(echo "$git_commit" | expand_git_ref); then
		exit 1
	fi
	header=$(echo -n "$header" | tag_remove git-commit)
fi

if [ "$opt_commit" ] && ! opt_commit=$(echo "$opt_commit" | expand_git_ref); then
	exit 1
fi

# command line > Git-commit > cherry
var_override commit "$cherry" "cherry picked from commit"
var_override commit "$git_commit" "Git-commit"
var_override commit "$opt_commit" "command line commit"

if [ -z "$commit" ]; then
	patch_subject=$(echo -n "$header" | tag_get subject | remove_subject_annotation)
	log_grep=$(git log --reverse --pretty="tformat:%h%x09%ai%x09%aN <%aE>%x09%s" -F --grep "$patch_subject" | grep -F "$patch_subject" || true)
	log_grep_nb=$(echo "$log_grep" | wc -l)
	if [ -n "$log_grep" -a $log_grep_nb -eq 1 ]; then
		log_grep_commit=$(echo "$log_grep" | awk '{print $1}' | expand_git_ref)
		var_override commit "$log_grep_commit" "git log --grep commit"
	elif [ -t 0 ]; then
		echo -n "Upstream commit id unknown for patch \"$patch_subject\", "
		if [ -z "$log_grep" ]; then
			echo "enter it now?"
		else
			echo "$log_grep_nb potential commits found in git log. Which one to use?"
			echo "$log_grep" | awk -F$'\t' '{print $1 "   " $2 "   " $3}'
		fi
		read -p "(<refspec>/empty cancels): " prompt_commit
		if [ "$prompt_commit" ]; then
			prompt_commit=$(echo "$prompt_commit" | expand_git_ref)
			var_override commit "$prompt_commit" "prompted commit"
		fi
	fi
fi

if [ -z "$commit" ]; then
	echo "Warning: Upstream commit id unknown, you will have to edit the patch header manually." > /dev/stderr
	header=$(echo -n "$header" | tag_add Git-commit "(fill me in)")
	edit=1
else
	commit_str=$commit
	if [ -n "${body%---}" ]; then
		cl_orig=$(git format-patch --stdout -p $commit^..$commit | cheat_diffstat | diffstat -lp1 | wc -l)
		cl_patch=$(echo -n "${body%---}" | cheat_diffstat | diffstat -lp1 | wc -l)
		if [ $cl_orig -ne $cl_patch ]; then
			commit_str+=" (partial)"
		fi
	fi
	header=$(echo -n "$header" | tag_add Git-commit "$commit_str")

	git_describe=$(git describe --contains --match "v*" $commit 2>/dev/null || true)
	git_describe=${git_describe%%[~^]*}
	if [ -z "$git_describe" ]; then
		git_describe="Queued in subsystem maintainer repository"
		result=$(git describe --contains --all $commit)
		if echo "$result" | grep -Eq "^remotes/"; then
			remote=$(echo "$result" | cut -d/ -f2)
		else
			branch=${result%%[~^]*}
			if [ $branch = "stash" ]; then
				echo "Error: cannot use stash to describe patch. Stopping to avoid possibly erroneous results." > /dev/stderr
				exit 1
			else
				if ! remote=$(git config --get branch.$branch.remote); then
					echo "Error: \"$branch\" does not look like a remote tracking branch. Failed to get information about repository URL." > /dev/stderr
					exit 1
				fi
			fi
		fi
		describe_url=$(git config --get remote.$remote.url)
	fi
fi


# Patch-mainline:

patch_mainline=$(echo -n "$header" | tag_get patch-mainline)
header=$(echo -n "$header" | tag_remove patch-mainline)

# Sometimes the tag does not include -rcX, I prefer to have it
# var_override can take care of it, but it will generate a warning
if [ "$patch_mainline" = "${git_describe%-rc*}" ]; then
	patch_mainline=$git_describe
fi

# git describe > Patch-mainline
var_override ml_status "$patch_mainline" "Patch-mainline"
var_override ml_status "$git_describe" "git describe result"

if [ -z "$ml_status" ]; then
	echo "Warning: Mainline status unknown, you will have to edit the patch header manually." > /dev/stderr
	header=$(echo -n "$header" | tag_add Patch-mainline "(fill me in)")
	edit=1
else
	header=$(echo -n "$header" | tag_add Patch-mainline "$ml_status")
fi


# Git-repo:

git_repo=$(echo -n "$header" | tag_get git-repo)
header=$(echo -n "$header" | tag_remove git-repo)

# git config > Git-repo
var_override remote_url "$git_repo" "Git-repo"
var_override --allow-empty remote_url "$describe_url" "git describe and remote configuration"

if [ -n "$remote_url" ]; then
	header=$(echo -n "$header" | tag_add Git-repo "$remote_url")
fi


# Patch-filtered:
# may be added by the exportpatch tool
header=$(echo -n "$header" | tag_remove patch-filtered)


# References:

cherry=$(echo "$header" | tag_get "cherry picked for")
if [ "$cherry" ]; then
	header=$(echo -n "$header" | tag_remove "cherry picked for")
fi

references=$(echo -n "$header" | tag_get --last references)
if [ "$references" ]; then
	header=$(echo -n "$header" | tag_remove --last references)
fi

# command line > References > cherry > command line (soft)
var_override ref "$opt_soft"
var_override ref "$cherry" "cherry picked for"
var_override ref "$references" "References"
var_override ref "$opt_ref" "command line reference"

if [ -z "$ref" ]; then
	echo "Warning: Reference information unknown, you will have to edit the patch header manually." > /dev/stderr
	header=$(echo -n "$header" | tag_add References "(fill me in)")
	edit=1
else
	header=$(echo -n "$header" | tag_add --last References "$ref")
fi


if [ -n "$commit" ]; then
	original_header=$(git format-patch --stdout -p $commit^..$commit | awk -f "$libdir"/patch_header.awk && echo ---)


	# Clean From:

	patch_from=$(echo -n "$header" | tag_get --last from)
	header=$(echo -n "$header" | tag_remove --last from)
	original_from=$(echo -n "$original_header" | tag_get --last from)

	# git format-patch > From
	var_override from "$patch_from" "patch file From:"
	var_override from "$original_from" "git format-patch From:"

	header=$(echo -n "$header" | tag_add --last From "$from")


	# Clean Date:

	patch_date=$(echo -n "$header" | tag_get date)
	header=$(echo -n "$header" | tag_remove date)
	original_date=$(echo -n "$original_header" | tag_get date)

	# git format-patch > date
	var_override date "$patch_date" "patch file Date:"
	var_override date "$original_date" "git format-patch Date:"

	header=$(echo -n "$header" | tag_add Date "$date")


	# Clean Subject:

	patch_subject=$(echo -n "$header" | tag_get subject | remove_subject_annotation)
	original_subject=$(echo -n "$original_header" | tag_get subject | remove_subject_annotation)

	# git format-patch > Subject
	var_override subject "$patch_subject" "patch file Subject:"
	var_override subject "$original_subject" "git format-patch Subject:"

	if [ "$original_subject" != "$patch_subject" ]; then
		header=$(echo -n "$header" | tag_remove subject)
		header=$(echo -n "$header" | tag_add Subject "$subject")
	fi
	# else ... keep the changes lower between the original patch file and
	# the cleaned one
fi


# Clean attributions

# this may be added by exportpatch in its default configuration
header=$(echo -n "$header" | grep -vF "Acked-by: Your Name <user@business.com>")

patch_attributions=$(echo -n "$header" | get_attributions)
if [ -n "$commit" ]; then
	original_attributions=$(echo -n "$original_header" | get_attributions)
	missing=$(grep -vf <(echo "$patch_attributions") <(echo "$original_attributions") || true)
	count=$(echo -n "$missing" | wc -l)
	if [ $count -gt 0 ]; then
		echo "Warning: $count attribution lines missing from the patch file. Adding them." > /dev/stderr
		header=$(echo -n "$header" | insert_attributions "$missing")
	fi
fi


# Add Acked-by:

name=$(git config --get user.name)
email=$(git config --get user.email)

if [ -z "$name" -o -z "$email" ]; then
	name_str=${name:-(empty name)}
	email_str=${email:-(empty email)}
	echo "Warning: user signature incomplete ($name_str <$email_str>), you will have to edit the patch header manually. Check the git config of the repository in $git_dir." > /dev/stderr
	name=${name:-Name}
	email=${email:-user@example.com}
	edit=1
fi
signature="$name <$email>"

patterns=$signature
patterns+=($opt_skip)
if ! echo -n "$header" | get_attribution_names | grep -qF "$(printf "%s\n" "${patterns[@]}")"; then
	header=$(echo -n "${header%---}" | tag_add Acked-by "$signature" && echo ---)
fi


if [ -n "$edit" ]; then
	if [ ! -t 0 ]; then
		echo "Warning: input is not from a terminal, cannot edit header now." > /dev/stderr
	else
		tmpfile=
		trap '[ -n "$tmpfile" -a -f "$tmpfile" ] && rm "$tmpfile"' EXIT
		tmpfile=$(mktemp --tmpdir clean_header.XXXXXXXXXX)
		echo -n "${header%---}" > "$tmpfile"
		$EDITOR "$tmpfile"
		header=$(cat "$tmpfile" && echo ---)
		rm "$tmpfile"
		trap - EXIT
	fi
fi

if [ -n "$filename" ]; then
	exec 1>"$filename"
fi
echo -n "${header%---}"
echo -n "${body%---}"
