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

		open LOG, "cvs log $name |" or die "Unable to run cvs log: $!\n";
		while (<LOG>) {
			# date: 2004-09-30 09:11:50 +0000;  author: olh;  state: Exp;
			next unless (/^date.*author:\s*(\S+);/o);
			$user = $1;
		}
		close LOG;

		printf "+%-6s\t$name$rest\n", $user;
		next;
	}
	print "$line\n";
}
