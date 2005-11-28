#!/usr/bin/perl
#
# Usage
#   patch-classify.pl [-v] [-k kernel_rev] cvs_rev1 cvs_rev2 file ...
#   patch-classify.pl [-v] [-k kernel_rev] [-P patchdir] -p cvs_rev1 file ...
#
# cvs_rev1 and cvs_rev2 are the CVS revisions to be compared.
#	Usually, these should be symbolic names (branch names
#	are allowed), but numeric revs work as well.
# -k kernel_rev
#	will ignore all patches that have a Patch-mainline tag
#	which specifies a kernel rev not later than kernel_rev.
# -r
#	Report patches that need review.
#	This assumes cvs_rev1 is an older branch and cvs_rev2
#	is the target branch that we want to update.
#	This will omit any patch from the report that
#	 -	is unchanged from the source branch
#	 -	has been killed in the target branch
#	 -	evolved from a version in the source branch
#	 -	does not exist in the source branch
# -p
#	Check whether the specified patches apply, or can be reverted.
#	Use the -P option to specific the location of the patch you
#	want to test
# -P patchdir
#	Directory to pick up the kernel patch files from. This should
#	be a checked out copy of cvs_rev1
# -v
#	Increase verbosity
#
# Useful things you can do with this script:
#
# 1. The following will spit out a one-patch-per-line list of patches
#    you will need to examine for inclusion in HEAD
#	HEAD_DIR=...
#	SP3_DIR=...
#	cd $HEAD_DIR
#	cat $SP3_DIR/series.conf | grep "patches.*/" |
#		./scripts/classify-patch.pl -r -k 2.6.14 -P $SP3_DIR SLES9_SP3_BRANCH HEAD
#    by adding -v, you can make the script spit out additional information
#
# 2. Feed the output of the above script into this command:
#	cat output-list |
#		./scripts/classify-patch.pl -p -k 2.6.14 -P $SP3_DIR SLES9_SP3_BRANCH
#    This will try to reverse or apply any patches from the first run and see if the
#    patch still applies, or has been merged fully.
#
# 3. Manually edit the list and cull "uninteresting" patches from this list.
#    You can then feed it into step 1
#

use Getopt::Std;

$STATE_START    = 0;
$STATE_BRANCHES = 1;


getopts('k:P:prv');
$opt_review  = $opt_r;
$opt_verbose = $opt_v;
$opt_patch   = $opt_p;
$patchdir    = $opt_P;
$patchdir   .= '/' if ($patchdir);
$kernel_rev  = $opt_k;

$tag0 = shift(@ARGV);
$tag1 = shift(@ARGV);

if (!$tag0 || !$tag1) {
	print STDERR "Usage: $ARGV0 tag0 tag1 files...\n";
}

die "Options -p and -r are mutually exclusive, abort\n"
		if ($opt_patch && $opt_review);

&guess_kernel_rev unless ($kernel_rev);
die "No kernel revision specified, and none divined\n"
		if ($opt_patch && !$kernel_rev);

if ($opt_patch) {
	my $scratch = $ENV{SCRATCH_AREA};
	my $basedir = "linux-$kernel_rev";
	my @try = (
		$basedir,
		"$scratch/$basedir",
		"$scratch/$basedir-$tag1",
	);

	foreach $try (@try) {
		if (-d $try) {
			$srcdir = $try;
			last;
		}
	}
	die "Cannot find kernel source dir $basedir\n" unless ($srcdir);
	print "Using source dir $srcdir\n" if ($opt_verbose);

	$patchcmd = "patch -p1 --quiet --force --dry-run --directory $srcdir >/dev/null";
}

foreach $patch (<>) {
	$patch =~ s/\n//;

	if ($patch =~ /^#/o || $patch =~ /^\s*$/o) {
		print "$patch\n";
		next;
	}

	# This little hack allows us to feed the output of
	# a previous script run back to it, without losing the
	# previous classification.
	# (eg you first do a CVS scan, then run classify-patch -p
	# to see which patches still apply)
	if ($patch =~ /([^:]*): (.*)/o) {
		$patch = $1;
		$original_comment = $2;
	}

	if ($opt_patch) {
		print "$patch: $original_comment";
		if (system("$patchcmd < $patchdir$patch") == 0) {
			print " [STILL APPLIES]";
		} elsif (system("$patchcmd -R < $patchdir$patch") == 0) {
			print " [APPARENTLY MERGED]";
		}
		print "\n";
		next;
	}

	open LOG, "cvs log $patch|" or die "Unable to start cvs log: $!\n";

	$verdict = '';
	$scanner = $STATE_START;
	%branch = ();
	%state = ();
	$dead = 0;

	while (<LOG>) {
		chop;
		if ($scanner == $STATE_BRANCHES) {
			if (/^\s+([^:]*):\s+(\S+)$/o) {
				$branch{$1} = $2;
				next;
			}
			$scanner = $STATE_START;
		}
		if (/^head: (\S+)/o) {
			$branch{'HEAD'} = $1;
			next;
		}
		if (/^symbolic names:/o) {
			$scanner = $STATE_BRANCHES;
			next;
		}
		last if (/^--/o);
	}

	($rev0, $branch0, $pattern0, $missing0) = &check_branch($tag0);
	($rev1, $branch1, $pattern1, $missing1) = &check_branch($tag1);
	($base_rev0, $base_rev1) = ($rev0, $rev1);

	($res, @common_base) = &rev_compare($rev0, $rev1);
	$common_base = join('.', @common_base);

	if ($missing0 || $missing1) {
		# Ignore patches missing from the source branch
		next if ($opt_review && $missing0);

		if ($missing0 && $missing1) {
			$verdict = "missing from both branches";
		} elsif ($missing0) {
			$verdict = "missing from branch $tag0";
		} else {
			$verdict = "missing from branch $tag1";
		}
		goto done;
	}

	$revision = '';
	while (<LOG>) {
		if (/^revision (\S+)/o) {
			$revision = $1;
			if ($pattern0 && $revision =~ /$pattern0/) {
				$rev0 = $revision;
				$pattern0 = '';
			}
			if ($pattern1 && $revision =~ /$pattern1/) {
				$rev1 = $revision;
				$pattern1 = '';
			}
			next;
		}
		next unless(/^date/o);

		if (/state:\s+([^;]+)/o) {
			$state{$revision} = $1;
		}
		if (/author:\s+([^;]+)/o) {
			$author{$revision} = $1;
		}
	}

	close LOG;

	$dead += 1 if ($state{$rev0} eq 'dead');
	$dead += 2 if ($state{$rev1} eq 'dead');

	# Special case: if the patch was never added to HEAD,
	# it's marked dead there.
	if ($dead && $state{'1.1'} eq 'dead') {
		if ($rev0 eq '1.1') {
			# Ignore patches missing from the source branch
			next if ($opt_review);
			$verdict = "missing from branch $tag0";
			goto done;
		}
		if ($rev1 eq '1.1') {
			$verdict = "missing from branch $tag1";
			goto done;
		}
	}

	($res, @ignore) = &rev_compare($rev0, $rev1);

	# Ignore patches in the target branch that are
	# unchanged, or have evolved directly from the
	# patch in the source branch.
	next if ($opt_review && $res != 1 && $res != 3);

	if ($res == 0) {
		$verdict = "equal";
	} elsif ($res == 1) {
		$verdict = "$tag0 more recent than $tag1";
	} elsif ($res == 2) {
		$verdict = "$tag1 more recent than $tag0";
	} else {
		$verdict = "diverging";
	}

	if ($dead) {
		# Ignore patches killed in the target branch
		next if ($opt_review && ($dead & 2));

		if ($dead == 3) {
			$verdict = "completetely dead";
		} elsif ($dead == $res) {
			# One of the two branches is more recent,
			# and is dead
			if ($dead == 1) {
				$verdict = "killed in $tag0";
			} else {
				$verdict = "killed in $tag1";
			}
		} elsif ($dead == 1) {
			$verdict = "$tag0 is dead ($verdict)";
		} elsif ($dead == 2) {
			$verdict = "$tag1 is dead ($verdict)";
		}
	}

done:
	$complain = 0;
	$mainline = '';
	if ($kernel_rev && $dead != 3) {
		$rev = ($dead == 1)? $rev1 : $rev0;
		if (-f "$patchdir$patch") {
			open PATCH, "<$patchdir$patch" or die "$patchdir$patch: $!\n";
		} elsif (-f $patch) {
			open PATCH, "<$patch" or die "$patch: $!\n";
		} else {
			open PATCH, "cvs up -p -r$rev $patch 2>/dev/null|"
						or die "cvs up -p $patch: $!\n";
		}
		while (<PATCH>) {
			s/\s+$//o;
			if (/^Patch-mainline:\s+(.*)/oi
			 || /^Mainline:\s+(.*)/oi) {
				$mainline = $1;
				$mainline =~ s/ or earlier//o;
				$mainline =~ s/\+$//o;
				$mainline =~ s/-rc\d+//o;
				$mainline =~ s/-git\d+//o;
				#$mainline =~ s/-mm\d+//o;	# mm kernels don't count
				if ($mainline eq 'yes'
				 || $mainline eq 'obsolete'
				 || $mainline eq 'unneeded') {
					# Assume any mainline
					$mainline = 'current';
				}
				last;
			}
		}
		if ($mainline) {
			# We do not do the CVS rev compare here, but a
			# simple string compare - in CVS, 1.3.3 is not less that 1.4.1,
			# but in kernel rev numbering, 2.6.11.8 <= 2.6.14
			if ($mainline eq 'current'
			 || ($mainline =~ /^\d[0-9.]*$/o && $mainline <= $kernel_rev)) {
				next if ($opt_review);
				$verdict = "ignored (merged into mainline in $mainline)";
			}
		} else {
			$complain = 1;
		}
			
		close PATCH;
	}

	print "$patch: $verdict\n";
	if ($opt_verbose) {
		printf "  %-20s %s\n", $tag0, &rev_print($rev0, $base_rev0, $branch0);
		printf "  %-20s %s\n", $tag1, &rev_print($rev1, $base_rev1, $branch1);
		printf "  %-20s %s\n", "common base rev", $common_base;
		if ($mainline) {
			printf "  %-20s %s\n", "mainline since", $mainline;
		}
		if ($opt_verbose > 1 && $complain) {
			print "  Patch doesn't have a patch-mainline tag\n";
		}
	}
}

sub check_branch {
	local($name) = @_;

	if ($name =~ /^\d/o) {
		return ($name, '', 0);
	}

	my $rev = $branch{$name};
	if (!$rev) {
		return ('', '', 1);
	}
	if ($rev =~ /^(.*)\.0\.(\d+)$/o) {
		my $base_rev = "$1";
		my $branch_rev = "$1.$2";
		my $match = "^$1.$2.";
		$match =~ s/\./\\./go;
		return ($base_rev, $branch_rev, $match, 0);
	}
	return ($rev, '', '', 0);
}

sub rev_print {
	local($rev, $base, $branch) = @_;
	my $msg = $rev;

	$msg .= ", branch $branch" if ($rev ne $base);
	$msg .= ", state $state{$rev}" if ($state{$rev} ne 'Exp');
	$msg .= ", by $author{$rev}" if ($author{$rev});
	return $msg;
}

# Compare two revisions.
# returns ($code, @common), where $code is
#   0	equal
#   1	$rev0 is more recent than base revision
#   2	$rev1 is more recent than base revision
#   3   revisions are different
sub rev_compare {
	local($rev0, $rev1) = @_;

	# Bail out if there is anything other that digits and dots in it
	return 3 unless ($rev0 =~ /^[.0-9]+$/o && $rev1 =~ /^[.0-9]+$/o);

	my @rev0 = split(/\./, $rev0);
	my @rev1 = split(/\./, $rev1);
	my @base;
	my $diff = 0;
	while (@rev0 && @rev1) {
		my $t0 = shift(@rev0);
		my $t1 = shift(@rev1);
		if ($t0 < $t1) {
			push(@base, $t0);
			$diff = 2;
			last;
		}
		if ($t1 < $t0) {
			push(@base, $t1);
			$diff = 1;
			last;
		}
		push(@base, $t0);
	}
	$diff |= 1 if (@rev0);
	$diff |= 2 if (@rev1);

	unshift @base, $diff;
	return @base;
}

sub guess_kernel_rev {
	open CFG, "<scripts/config.sh" or return;

	while (<CFG>) {
		if (/SRCVERSION=(.*)/o) {
			$kernel_rev = $1;
			last;
		}
	}
	close CFG;
}
