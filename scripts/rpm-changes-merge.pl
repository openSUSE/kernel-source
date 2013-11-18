#!/usr/bin/env perl
#############################################################################
# Copyright (c) 2008,2009 Novell, Inc.
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
#
# script to merge changes done to *.changes files
#
# To install the script as a git merge driver:
#
#   git config merge.rpm-changes.name "*.changes merge driver"
#   git config merge.rpm-changes.driver "scripts/rpm-changes-merge.pl %A %O %B"
#   echo '*.changes merge=rpm-changes' >>.git/info/attributes

use strict;
use warnings;

BEGIN {
    if ($0 =~ /^(.*)\/[^\/]*/) {
        unshift @INC, "$1/lib";
    } else {
        unshift @INC,  "./lib";
    }
}
use Time::Zone;
use Getopt::Std;
use POSIX qw(mktime);
use File::Temp qw(tempfile);

my $conflicts = 0;

sub usage {
    print STDERR
"Usage:
  Three-way merge:
    $0 [-p] my.changes orig.changes their.changes
  Two-way merge:
    $0 [-p] -2 my.changes their.changes
  Fixup mode:
    $0 [-p] -1 my.changes
";
    exit 1;
}

sub main {
    $ENV{'TZ'} = "UTC";

    our ($opt_p, $opt_1, $opt_2, $opt_3) = (0, 0, 0, 0);
    my (%O, %A, %B, $out);
    if (!getopts('p123') || $opt_1 + $opt_2 + $opt_3 > 1) {
        usage();
    }
    if ($opt_1) {
        usage() if @ARGV != 1;
        loadchanges($ARGV[0], \%A);
    } elsif ($opt_2) {
        usage() if @ARGV != 2;
        loadchanges($ARGV[0], \%A);
        loadchanges($ARGV[1], \%B);
    } else {
        usage() if @ARGV != 3;
        loadchanges($ARGV[0], \%A);
        loadchanges($ARGV[1], \%O);
        loadchanges($ARGV[2], \%B);
    }
    if ($opt_p) {
        $out = \*STDOUT;
    } else {
        open($out, '>', $ARGV[0]) or die "$ARGV[0]: $!\n";
    }

    my %seen;
    for my $key (reverse(sort(keys(%A), keys(%O), keys(%B)))) {
        next if $seen{$key};
        $seen{$key} = 1;
        print $out merge($A{$key}, $O{$key}, $B{$key});
    }
    exit $conflicts;
}

sub merge {
    my ($a, $o, $b) = @_;
    $a = "" unless defined $a;
    $o = "" unless defined $o;
    $b = "" unless defined $b;
    return $a if $a eq $b;
    return $a if $o eq $b;
    return $b if $o eq $a;
    return rcs_merge($a, $o, $b);
}

my $have_rcs_merge = 1;
sub rcs_merge {
    my @texts = @_;
    my $res;
    if ($have_rcs_merge) {
        my @fh;
        my @fn;
        for my $i (0..2) {
            ($fh[$i], $fn[$i]) = tempfile();
            my $fh = $fh[$i];
            print $fh $texts[$i];
        }
        $res = `merge -p $fn[0] $fn[1] $fn[2]`;
        for my $i (0..2) {
            close($fh[$i]);
            unlink($fn[$i]);
        }
        if ($? == 0) {
            return $res;
        } elsif ($? >> 8 == 1) {
            $conflicts = 1;
            return $res;
        } else {
            print STDERR "merge(1) not found, using DumbMerge(TM) instead.\n";
            print STDERR "Install the rcs package for better merge results.\n";
            $have_rcs_merge = 0;
        }
    }
    return "<<<<<<< $ARGV[0]\n" . $texts[0] . "=======\n" . $texts[2] . ">>>>>>> $ARGV[2]\n";
}

sub loadchanges {
    my ($file, $res) = @_;
    open(my $fh, '<', $file) or die "$file: $!\n";
    my $l;
    my $date = 1<<32;
    my $email = "";
    my $expect_date = 0;
    my $text;
    while ($l = <$fh>) {
        if ($expect_date) {
            (my $dt, $email) = parse_date($l);
            if (defined $dt) {
                $date = $dt;
            } else {
                print STDERR "$file:$.: invalid date: $l";
            }
            $expect_date = 0;
        }
        if ($l =~ /^-{50}-*$/ || eof($fh)) {
            if (eof($fh)) {
                $text .= $l;
            }
            if (defined $text) {
                my $key = sprintf("%010d %s", $date, $email);
                if (defined $res->{$key}) {
                    $res->{$key} .= $text;
                } else {
                    $res->{$key} = $text
                }
            }
            undef $text;
            $date--;
            $expect_date = 1;
        }
        $text .= $l;
    }
    close($fh)
}

my %monthnum = (
    jan => 0,
    feb => 1,
    mar => 2,
    apr => 3,
    may => 4,
    jun => 5,
    jul => 6,
    aug => 7,
    sep => 8,
    oct => 9,
    nov => 10,
    dec => 11,
);

sub parse_date {
    my $l = shift;
    if ($l !~ /^(?:mon|tue|wed|thu|fri|sat|sun) +(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec) +(\d+) +(\d\d):(\d\d):(\d\d) +([A-Z]+) +(\d\d\d\d) +- +([^ ]*) *$/i) {
        return (undef, "");
    }
    my ($b, $d, $H, $M, $S, $Z, $Y, $email) = ($1, $2, $3, $4, $5, $6, $7, $8);
    my $date = mktime($S, $M, $H, $d, $monthnum{lc $b}, $Y - 1900);
    return (undef, "") unless defined $date;
    my $offset = tz_offset($Z);
    return (undef, "") unless defined $offset;
    chomp $email;
    return ($date - $offset, $email);
}

main();

# vim: sw=4:et
