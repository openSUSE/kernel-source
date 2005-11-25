#!/usr/bin/perl
#
# Run this script on series.conf to find out who originated
# what patch. Dreadfully slow if run over ssh, but effective :)
#
# Output will look like this
#
# +user	patches.foobar/original-patch-name
#

while (<>) {
	chop;
	$line = $_;
	if (/^\s+(patches\.\S*)(.*)/o) {
		$name = $1;
		$rest = $2;
		$user = "anyone";

		$user = &get_author($name);
		if (!$user) {
			$user = &get_committer($name);
		}

		printf "+%s\t$name$rest\n", $user;
		next;
	}
	print "$line\n";
}

sub get_author {

	local($patch) = @_;
	my $user = '';

	open PATCH, "<$patch" or return '';
	while (<PATCH>) {
		last if (/^--- /o);
		if (/^From: (.*\@suse.*)/o
		 || /^Signed-off-by: (.*\@suse.*)/o
		 || /^Acked-by: (\S.*\@suse.*)/o) {
		 	$user = $1;
			$user =~ s/.*<([^>]*)>.*/\1/o;
			$user =~ s/\@.*//o;
			last;
		}
	}
	close PATCH;
	return $user;
}

sub get_committer {
	local($patch) = @_;
	my $user = '';

	open LOG, "cvs log $patch |" or die "Unable to run cvs log: $!\n";
	while (<LOG>) {
		# date: 2004-09-30 09:11:50 +0000;  author: olh;  state: Exp;
		next unless (/^date.*author:\s*(\S+);/o);
		$user = $1;
	}
	close LOG;

	return $user;
}
