#!/usr/bin/perl

use File::Spec;
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
	# Normalize file path, mainly to strip away the ending forward slash,
	# or any double forward slashes.
	my $loc = File::Spec->canonpath(shift @_);
	# We cannot use an absolute path (e.g. /usr/src/linux-5.14.21-150500.41)
	# during find because it's under build root, but rpm wants one later.
	my $abs_loc = rpm_path($loc);
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
		my $abs_path = rpm_path($_);
		$is_devel ? push(@dev, $abs_path) : push(@ndev, $abs_path);
	}

	push(@dev, &calc_dirs($abs_loc, \@dev));
	push(@ndev, &calc_dirs($abs_loc, \@ndev));
	return (\@dev, \@ndev);
}

sub calc_dirs
{
	my($base, $files) = @_;
	my %dirs;

	foreach my $file (@$files) {
		my ($volume,$path,$basename) = File::Spec->splitpath($file);
		my @dirs = File::Spec->splitdir($path);
		do {
			# Always create $path from catdir() to avoid ending forward slash
			$path = File::Spec->catdir(@dirs);
			$dirs{$path} = 1;
			pop @dirs;
		} while ($path ne $base);
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

sub rpm_path
{
	my $path = shift @_;
	# Always prepend forward slash and let canonpath take care of
	# duplicate forward slashes.
	return File::Spec->canonpath("/$path");
}
