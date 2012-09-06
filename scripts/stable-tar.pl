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
for my $file (sort(@files)) {
	my $header = "";

	my $prefix = "";
	my $name = $file;
	if (length($file) > 100) {
		($prefix = $file) =~ s:/[^/]*$::;
		($name = $file) =~ s:^.*/::;
		if (length($name) > 100 || length($prefix) > 155) {
			# We could generate a pax extended header with a path
			# keyword, but let's hope that all developers are sane
			# enough not to use such long filenames for their
			# patches
			die "Long filenames not supported: $file";
		}
	}
	my @stat = lstat($file) or die "$file: $!\n";
	my $mode = $stat[2];
	my $size = 0;
	my $typeflag;
	my $linktarget = "";
	if (S_ISREG($mode)) {
		$size = $stat[7];
		$typeflag = "0";
	} elsif (S_ISLNK($mode)) {
		$linktarget = readlink($file);
		$typeflag = "2";
	} elsif (S_ISDIR($mode)) {
		$typeflag = "5";
	} else {
		die "Only regular files, symlinks and directories supported: $file\n";
	}

	# HEADER
	# name
	$header = pad($name, 100);
	# mode
	$header .= pad_octal(($mode & 0111) ? 0755 : 0644, 8);
	# uid and gid; we use 65534 and 65534, which is commonly used for
	# nobody:nobody
	$header .= pad_octal(65534, 8);
	$header .= pad_octal(65533, 8);
	# size
	$header .= pad_octal($size, 12);
	# mtime
	$header .= pad_octal($mtime, 12);
	# checksum placeholder
	my $checksum_pos = length($header);
	$header .= " " x 8;
	# type flag
	$header .= $typeflag;
	# name of linked file
	$header .= pad($linktarget, 100);
	# magic
	$header .= pad("ustar", 6);
	# version
	$header .= "00";
	# user and group
	$header .= pad("nobody", 32);
	$header .= pad("nobody", 32);
	# device major and minor
	$header .= pad_octal(0, 8);
	$header .= pad_octal(0, 8);
	# prefix
	$header .= pad($prefix, 155);
	# add the checksum, using the "%06o\0 " format like GNU tar
	my $csum = header_checksum($header);
	substr($header, $checksum_pos, 7) = pad_octal($csum, 7);
	# padding to 512 byte boundary
	$header .= pad("", 12);
	die "error: header is not 512 bytes long" unless length($header) == 512;
	print $header;
	$total_size += 512;
	next unless S_ISREG($mode);

	# PAYLOAD
	copy($file, \*STDOUT);
	$total_size += $size;
	# padding to 512 byte boundary
	if ($size % 512) {
		my $padding = 512 - $size % 512;
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

