#!/usr/bin/perl

#############################################################################
# Copyright (c) 2012 Novell, Inc.
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

# A very limited tar writer. Creates archives in the ustar format and
# makes sure that identical content results in identical archives.

use strict;
use warnings;

my $USAGE = "Usage: $0 --mtime=<decimal timestamp> [--exclude=<pattern] [-C directory] file|directory ... >archive.tar\n";

use Getopt::Long;
use File::Find;
use File::Copy;
use Fcntl ':mode';

my $mtime = 0;
my $chdir;
my @exclude = ();
GetOptions(
	"t|mtime=i" => \$mtime,
	"exclude=s" => \@exclude,
	"C=s" => \$chdir,
) or die($USAGE);
die $USAGE unless @ARGV;

warn "$0: --mtime not specified, using the beginning of the epoch\n" unless $mtime;

chdir($chdir) if $chdir;
my @files;

s/\*/.*/g for @exclude;
s/\?/./g for @exclude;
sub wanted {
	for my $pattern (@exclude) {
		return if $_ =~ $pattern;
	}
	push(@files, $File::Find::name);
}

for my $file (@ARGV) {
	if (-d $file) {
		find(\&wanted, $file);
	} else {
		push(@files, $file);
	}
}
$| = 1;
my $total_size = 0;

# Tar header format description
# filed => <width><type>
# where type is either _s_string or _o_ctal
my @header_layout = (
	name => "100s",
	mode => "8o",
	uid => "8o",
	gid => "8o",
	size => "12o",
	mtime => "12o",
	csum => "8s",
	typeflag => "1s",
	linktarget => "100s",
	magic => "6s",
	version => "2s",
	user => "32s",
	group => "32s",
	devmajor => "8o",
	devminor => "8o",
	prefix => "155s"
);

for my $file (sort(@files)) {
	my %header = ();

	$header{name} = $file;
	if (length($file) > 100) {
		($header{prefix} = $file) =~ s:/[^/]*$::;
		($header{name} = $file) =~ s:^.*/::;
		if (length($header{name}) > 100 ||
					length($header{prefix}) > 155) {
			# We could generate a pax extended header with a path
			# keyword, but let's hope that all developers are sane
			# enough not to use such long filenames for their
			# patches
			die "Long filenames not supported: $file";
		}
	}
	my @stat = lstat($file) or die "$file: $!\n";
	my $mode = $stat[2];
	$header{mode} = ($mode & 0111) ? 0755 : 0644;
	if (S_ISREG($mode)) {
		$header{size} = $stat[7];
		$header{typeflag} = "0";
	} elsif (S_ISLNK($mode)) {
		$header{linktarget} = readlink($file);
		$header{typeflag} = "2";
	} elsif (S_ISDIR($mode)) {
		$header{typeflag} = "5";
	} else {
		die "Only regular files, symlinks and directories supported: $file\n";
	}
	# 65534:65534 is commonly used for nobody:nobody
	$header{uid} = 65534;
	$header{gid} = 65533;
	$header{user} = "nobody";
	$header{group} = "nobody";

	$header{mtime} = $mtime;

	print gen_header(\%header);
	$total_size += 512;
	next unless S_ISREG($mode);

	# PAYLOAD
	copy($file, \*STDOUT);
	$total_size += $header{size};
	# padding to 512 byte boundary
	if ($header{size} % 512) {
		my $padding = 512 - $header{size} % 512;
		$total_size += $padding;
		print pad("", $padding);
	}
}
# end of archive marker
print pad("", 1024);
$total_size += 1024;
# pad to 10240 boundary
if ($total_size % 10240) {
	print pad("", 10240 - $total_size % 10240);
}
exit;

sub gen_header {
	my $header = shift;

	$header->{magic} = "ustar";
	$header->{version} = "00";

	my $res = "";
	my $csum_pos = 0;
	for (my $i = 0; $i < scalar(@header_layout); $i += 2) {
		my $field = $header_layout[$i];
		my $fmt = $header_layout[$i + 1];
		(my $length = $fmt) =~ s/.$//;
		(my $type = $fmt) =~ s/^\d*//;
		my $value = $header->{$field};

		# special case
		if ($field eq "csum") {
			$csum_pos = length($res);
			$res .= " " x 8;
			next;
		}
		if ($type eq "s") {
			$value = "" unless defined($value);
			$res .= pad($value, $length);
		} elsif ($type eq "o") {
			$value = 0 unless defined($value);
			$res .= pad_octal($value, $length);
		} else {
			die "Invalid format for $field: $fmt";
		}
	}
	# add the checksum, using the "%06o\0 " format like GNU tar
	my $csum = header_checksum($res);
	substr($res, $csum_pos, 7) = pad_octal($csum, 7);

	# padding to 512 byte boundary
	$res .= pad("", 12);
	die "error: header is not 512 bytes long" unless length($res) == 512;

	return $res;
}

sub pad {
	my ($string, $length) = @_;
	
	my $pad = $length - length($string);
	if ($pad < 0) {
		die "Field over $length bytes: $string\n";
	}
	return $string . "\0" x $pad;
}

sub pad_octal {
	my ($num, $length) = @_;

	$length--;
	return sprintf("%0${length}o\0", $num);
}

sub header_checksum {
	my $header = shift;

	my $res = 0;
	for (my $i = 0; $i < length($header); $i++) {
		$res += ord(substr($header, $i, 1))
	}
	return $res;
}

