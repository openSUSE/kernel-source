#!/usr/bin/perl
use strict;
use warnings;

use Getopt::Long;
use Data::Dumper;

# ( { sym => regexp, mod => regexp, fail => 0/1 }, ... )
my @rules;
my ($opt_verbose, $opt_rules);

# if Module.symvers also lists namespaces (>=5.4)
my $use_namespaces;

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

		# If it matches a module path or vmlinux
		if ($pattern =~ /\/|^vmlinux$/) {
			$new->{mod} = $pattern;
		# If it's not a path and the string is all uppercase, assume it's a namespace
		} elsif ($use_namespaces &&
			$pattern !~ /\// && $pattern eq uc($pattern)) {
			$new->{namespace} = $pattern;
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

# Return 1 if using new (>=5.4) Module.symvers format with namespaces
sub symvers_uses_namespaces {
	my $file = shift;
	xopen(my $fh, '<', $file);
	my $line =  <$fh>;
	chomp $line;

	# If there are 5 tab delimited fields, then it's a newer (>=5.4)
	# Module.symvers format with namespaces. The older Module.symvers
	# format only has 4 fields (crc, symbol, module, export type).
	my @l =  split(/\t/, $line);
	if (@l > 4) {
		return 1;
	} else {
		return 0;
	}
}

sub load_symvers {
	my $file = shift;
	my %res;
	my $errors = 0;
	my $new;

	xopen(my $fh, '<', $file);
	while (<$fh>) {
		chomp;
		my @l = split(/\t/);
		if (@l < 4) {
			print STDERR "$file:$.: unknown line\n";
			$errors++;
			next;
		}
		if ($use_namespaces) {
			$new = { crc => $l[0], namespace => $l[2], mod => $l[3], type => $l[4] };
		} else {
			$new = { crc => $l[0], mod => $l[2], type => $l[3] };
		}
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
	my ($sym, $symvers, $message) = @_;
	my $fail = 1;

	for my $rule (@rules) {
		if ($rule->{mod} && $symvers->{mod} =~ $rule->{mod} ||
		    $rule->{sym} && $sym =~ $rule->{sym} ||
			($use_namespaces && $rule->{namespace} &&
				$symvers->{namespace} =~ $rule->{namespace})) {
			$fail = $rule->{fail};
			last;
		}
	}
	return unless $fail or $opt_verbose;

	print STDERR "KABI: symbol $sym(mod:$symvers->{mod}";
	if ($use_namespaces && $symvers->{namespace}) {
		print STDERR " ns:$symvers->{namespace}";
	}
	print STDERR ") $message";
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

# Determine symvers format
$use_namespaces = symvers_uses_namespaces($ARGV[0]);

if (defined($opt_rules)) {
	load_rules($opt_rules);
}
my %old = load_symvers($ARGV[0]);
my %new = load_symvers($ARGV[1]);

for my $sym (sort keys(%old)) {
	if (!$new{$sym}) {
		kabi_change($sym, $old{$sym}, "lost");
	} elsif ($old{$sym}->{crc} ne $new{$sym}->{crc}) {
		kabi_change($sym, $old{$sym}, "changed crc from " .
			"$old{$sym}->{crc} to $new{$sym}->{crc}");
	} elsif (!type_compatible($old{$sym}->{type}, $new{$sym}->{type})) {
		kabi_change($sym, $old{$sym}, "changed type from " .
			"$old{$sym}->{type} to $new{$sym}->{type}");
	}
}
if ($kabi_errors) {
	print STDERR "KABI: aborting due to kabi changes.\n";
	exit 1;
}
exit 0;
