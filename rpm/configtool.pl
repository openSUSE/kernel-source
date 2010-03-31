#!/usr/bin/perl
#
# Merge two kernel configs, eliminating duplicated assignments.
# TODO:
#   support for #include-style directives in config files, to make the
#   kernel configs more maintainable

use strict;
use warnings;

# ( { source => <file> name => ... value => ...}, { comment => ...}, ... )
my @lines;
# references into the @lines array
my %variables;

sub store_var {
	my ($file, $line, $name, $value) = @_;

	if (exists($variables{$name})) {
		if ($variables{$name}->{source} eq $file) {
			print STDERR "$file:$line: warning: $name redefined\n";
		}
	} else {
		my $new = {};
		push(@lines, $new);
		$variables{$name} = $new;
	}
	$variables{$name}->{source} = $file;
	$variables{$name}->{name} = $name;
	$variables{$name}->{value} = $value;
}

sub store_comment {
	my ($comment) = @_;

	push(@lines, { comment => $comment });
}

while (<>) {
	chomp;
	if (/^CONFIG_(\w+)=(.*)/) {
		store_var($ARGV, $., $1, $2);
	} elsif (/^# CONFIG_(\w+) is not set/) {
		store_var($ARGV, $., $1, 'n');
	} elsif (/^$|^#/) {
		store_comment($_);
	} else {
		print STDERR "$ARGV:$.: warning: ignoring unknown line\n";
	}
}

for my $line (@lines) {
	if (exists($line->{comment})) {
		print "$line->{comment}\n";
	} elsif ($line->{value} eq 'n') {
		print "# CONFIG_$line->{name} is not set\n";
	} else {
		print "CONFIG_$line->{name}=$line->{value}\n";
	}
}
