#!/usr/bin/perl

use Getopt::Long;
use strict;

&main();
sub main
{
	my($dev_output, $ndev_output, $loc) = ("-", "-", ".");
	&Getopt::Long::Configure(qw(bundling));
	&GetOptions(
		"D=s" => \$dev_output,
		"N=s" => \$ndev_output,
		"L=s" => \$loc,
	);

	my($dev, $ndev) = &scan($loc);
	&output($dev, $ndev, $dev_output, $ndev_output);
}

sub scan
{
	my $loc = shift @_;
	my(@dev, @ndev);

	foreach $_ (`find "$loc"`)
	{
		chomp $_;
		if (-d $_ && !-l $_) {
			# Generate directory list later.
			next;
		}
		my $is_devel =
			m{^\Q$loc\E.*/Kconfig} ||
			m{^\Q$loc\E.*/Kbuild} ||
			m{^\Q$loc\E.*/Makefile} ||
			m{^\Q$loc\E/arch/[^/]+/boot/dts/include/dt-bindings\b} ||
			m{^\Q$loc\E/arch/[^/]+/include\b} ||
			m{^\Q$loc\E/arch/.*/module\.lds\b} ||
			m{^\Q$loc\E/arch/arm/[^/]+/include/mach\b} ||
			m{^\Q$loc\E/arch/arm/[^/]+/include/plat\b} ||
			m{^\Q$loc\E/arch/[^/]+/scripts\b} ||
			m{^\Q$loc\E/arch/[^/]+/tools\b} ||
			m{^\Q$loc\E/include/[^/]+\b} ||
			m{^\Q$loc\E/scripts\b};
		if (substr($_, 0, 1) ne "/") {
			# We cannot use an absolute path during find,
			# but rpm wants one later.
			$_ = "/$_";
		}
		$is_devel ? push(@dev, $_) : push(@ndev, $_);
	}

	push(@dev, &calc_dirs("/$loc", \@dev));
	push(@ndev, &calc_dirs("/$loc", \@ndev));
	return (\@dev, \@ndev);
}

sub calc_dirs
{
	my($base, $files) = @_;
	my %dirs;

	foreach my $file (@$files) {
		my $path = $file;
		do {
			$path =~ s{/[^/]+$}{};
			$dirs{$path} = 1;
		} while ($path ne $base and $path ne "");
		# This loop also makes sure that $base itself is included.
	}

	return map { "\%dir $_" } keys %dirs;
}

sub output
{
	my($dev, $ndev, $dev_out, $ndev_out) = @_;
	local *FH;

	open(FH, "> $dev_out") || warn "Error writing to $dev_out: $!";
	print FH join("\n", @$dev), "\n";
	close FH;

	open(FH, "> $ndev_out") || warn "Error writing to $ndev_out: $!";
	print FH join("\n", @$ndev), "\n";
	close FH;
}
