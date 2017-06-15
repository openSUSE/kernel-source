#!/usr/bin/perl
use strict;
use warnings;

use Getopt::Long;
use Data::Dumper;

# ( { sym => regexp, mod => regexp, fail => 0/1 }, ... )
my @rules;
my ($opt_verbose, $opt_rules);

sub load_rules {
	my $file = shift;
	my $errors = 0;

	xopen(my $fh, '<', $file);
	while (<$fh>) {
		chomp;
		s/#.*//;
		next if /^\s*$/;
		my ($pattern, $verdict) = split(/\s+/);
		my $new = {};
		if (uc($verdict) eq "PASS") {
			$new->{fail} = 0;
		} elsif (uc($verdict) eq "FAIL") {
			$new->{fail} = 1;
		} else {
			print STDERR "$file:$.: invalid verdict \"$verdict\", must be either PASS or FAIL.\n";
			$errors++;
			next;
		}
		# simple glob -> regexp conversion
		$pattern =~ s/\*/.*/g;
		$pattern =~ s/\?/./g;
		$pattern =~ s/.*/^$&\$/;
		if ($pattern =~ /\/|^vmlinux$/) {
			$new->{mod} = $pattern;
		} else {
			$new->{sym} = $pattern;
		}
		push(@rules, $new);
	}
	if ($errors && !@rules) {
		print STDERR "error: only garbage found in $file.\n";
		exit 1;
	}
	close($fh);
}

sub load_symvers {
	my $file = shift;
	my %res;
	my $errors = 0;

	xopen(my $fh, '<', $file);
	while (<$fh>) {
		my @l = split(/\s+/);
		if (@l < 3) {
			print STDERR "$file:$.: unknown line\n";
			$errors++;
			next;
		}
		my $new = { crc => $l[0], mod => $l[2], type => $l[3] };
		$res{$l[1]} = $new;
	}
	if (!%res) {
		print STDERR "error: no symvers found in $file.\n";
		exit 1;
	}
	close($fh);
	return %res;
}

# Each bit represents a restriction of the export and adding a restriction
# fails the check
my $type_GPL    = 0x1;
my $type_NOW    = 0x2;
my $type_UNUSED = 0x4;
my %types = (
	EXPORT_SYMBOL            => 0x0,
	EXPORT_SYMBOL_GPL        => $type_GPL | $type_NOW,
	EXPORT_SYMBOL_GPL_FUTURE => $type_GPL,
	EXPORT_UNUSED_SYMBOL     => $type_UNUSED,
	EXPORT_UNUSED_SYMBOL_GPL => $type_UNUSED | $type_GPL | $type_NOW
);

sub type_compatible {
	my ($old, $new) = @_;

	for my $type ($old, $new) {
		if (!exists($types{$type})) {
			print STDERR "error: unrecognized export type $type.\n";
			exit 1;
		}
	}
	# if $new has a bit set that $old does not -> fail
	return !(~$types{$old} & $types{$new});
}

my $kabi_errors = 0;
sub kabi_change {
	my ($sym, $mod, $message) = @_;
	my $fail = 1;

	for my $rule (@rules) {
		if ($rule->{mod} && $mod =~ $rule->{mod} ||
		    $rule->{sym} && $sym =~ $rule->{sym}) {
			$fail = $rule->{fail};
			last;
		}
	}
	return unless $fail or $opt_verbose;
	print STDERR "KABI: symbol $sym($mod) $message";
	if ($fail) {
		$kabi_errors++;
		print STDERR "\n";
	} else {
		print STDERR " (tolerated)\n";
	}
}

sub xopen {
	open($_[0], $_[1], @_[2..$#_]) or die "$_[2]: $!\n";
}

my $res = GetOptions(
	'verbose|v' => \$opt_verbose,
	'rules|r=s' => \$opt_rules,
);
if (!$res || @ARGV != 2) {
	print STDERR "Usage: $0 [--rules <rules file>] Module.symvers.old Module.symvers\n";
	exit 1;
}
if (defined($opt_rules)) {
	load_rules($opt_rules);
}
my %old = load_symvers($ARGV[0]);
my %new = load_symvers($ARGV[1]);

for my $sym (sort keys(%old)) {
	if (!$new{$sym}) {
		kabi_change($sym, $old{$sym}->{mod}, "lost");
	} elsif ($old{$sym}->{crc} ne $new{$sym}->{crc}) {
		kabi_change($sym, $old{$sym}->{mod}, "changed crc from " .
			"$old{$sym}->{crc} to $new{$sym}->{crc}");
	} elsif (!type_compatible($old{$sym}->{type}, $new{$sym}->{type})) {
		kabi_change($sym, $old{$sym}->{mod}, "changed type from " .
			"$old{$sym}->{type} to $new{$sym}->{type}");
	}
}
if ($kabi_errors) {
	print STDERR "KABI: aborting due to kabi changes.\n";
	exit 1;
}
exit 0;
