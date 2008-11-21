#!/usr/bin/env perl

use strict;
use warnings;
use diagnostics;

use Digest::MD5 qw(md5_hex);
use Getopt::Long;
use Data::Dumper;


our $usage = 
"Usage:
  $0 --list-exported-symbols ...
  $0 --generate-symsets [--reference=DIR] --output-dir=DIR ...
  $0 --list-symsets [--reference=DIR] ...
  $0 --check-kabi --reference=DIR ...
";
our ($opt_verbose);
our $kabi_badness = 0;
our (%commonsyms, %usedsyms, @severities);
our ($opt_list_exp, $opt_gen_sets, $opt_list_sets, $opt_check_kabi) = (0,0,0,0);
our ($opt_max_badness, $opt_commonsyms, $opt_usedsyms, $opt_severities);
our ($opt_output_dir, $opt_reference, $opt_modules, $opt_symvers_file);

sub main {
     my $res = GetOptions(
        'list-exported-symbols' => \$opt_list_exp,
        'generate-symsets' => \$opt_gen_sets,
        'list-symsets' => \$opt_list_sets,
        'check-kabi' => \$opt_check_kabi,

        'max-badness=i' => \$opt_max_badness,
        'commonsyms|common-syms=s' => \$opt_commonsyms,
        'usedsyms|used-syms=s' => \$opt_usedsyms,
        'severities=s' => \$opt_severities,

        'symvers-file=s' => \$opt_symvers_file,
        'modules=s' => \$opt_modules,
        'reference=s' => \$opt_reference,

        'output-dir=s' => \$opt_output_dir,
        'verbose|v' => \$opt_verbose,
    );
    # boring option checking
    my $opt_err = sub  {
        print STDERR "ERROR: @_\n";
        $res = 0;
    };
    &$opt_err("Please choose one of --list-exported-symbols, --generate-symsets, --list-symsets or --check-kabi")
        if ($opt_list_exp + $opt_gen_sets + $opt_list_sets > 1 ||
           !($opt_list_exp + $opt_gen_sets + $opt_list_sets + $opt_check_kabi));
    &$opt_err("--check-kabi doesn't work with --list-exported-symbols")
        if ($opt_list_exp && $opt_check_kabi);
    &$opt_err("--check-kabi requires --reference")
        if ($opt_check_kabi && !$opt_reference);
    &$opt_err("--output-dir only makes sense with --generate-symsets")
        if ($opt_output_dir && !$opt_gen_sets);
    &$opt_err("--generate-symsets requires --output-dir")
        if ($opt_gen_sets && !$opt_output_dir);
    if (!$opt_check_kabi) {
        for my $opt qw(max-badness commonsyms usedsyms severities) {
            no strict 'refs';
            my $var = "opt_$opt";
            $var =~ s/-/_/g;
            if (defined(${$var})) {
                &$opt_err("--$opt only makes sense with --check-kabi");
            }
        }
    }
    # get list of modules
    my @modules;
    if (defined($opt_modules)) {
        my $fh;
        if ($opt_modules eq '-') {
            open($fh, '<&STDIN');
        } else {
            open($fh, '<', $opt_modules) or die "Can't open module list $opt_modules: $!\n";
        }
        @modules = <$fh>;
        chomp(@modules);
        close($fh);
    } else {
        @modules = @ARGV;
    }
    if (@modules == 0) {
        &$opt_err("No modules supplied");
    }
    if (!$res) {
        print STDERR $usage;
        exit 1;
    }

    # get list of exports
    my @exports;
    for my $file (@modules) {
        push(@exports, module_exports($file));
    }
    if (defined($opt_symvers_file)) {
        push(@exports, builtin_exports(parse_symset($opt_symvers_file)));
    }
    if ($opt_list_exp) {
        print format_exports(@exports);
        exit 0;
    }

    # generate symsets and optionally check kabi
    my (@ref, @sets);
    @sets = split_into_symsets(@exports);
    if (defined($opt_reference)) {
        @ref = load_symsets($opt_reference);
        if ($opt_check_kabi) {
            load_kabi_files($opt_commonsyms, $opt_usedsyms, $opt_severities);
        }
        # records kabi breakage if $opt_check_kabi is set
        preserve_symsets(\@ref, \@sets);
    }
    if ($opt_gen_sets) {
        write_symsets($opt_output_dir, @sets);
    } elsif ($opt_list_sets) {
        write_symsets(undef, @sets);
    }
    if ($kabi_badness) {
        print STDERR "KABI: badness is $kabi_badness";
        if (!defined($opt_max_badness) || $kabi_badness <= $opt_max_badness) {
            print STDERR " (tolerated)\n";
        } else {
            print STDERR " (exceeds threshold $opt_max_badness), aborting\n";
            exit 1;
        }
    }
    exit 0;
}

# structures used:
# %export: 
#   (crc => $crc, sym => $sym, mod => $module, type => $type)
# @exportlist
#   ({crc => $crc, sym => $sym, mod => $module, type => $type}, ...)
# @symset:
#   ($name, [{crc => $crc, sym => $sym, mod => $module, type => $type}, ...])
# @symsetlist:
#   (
#     [$name, [{crc => $crc, sym => $sym, mod => $module, type => $type}, ...],
#     ...
#   )
#     

# parse a Modules.symvers-style file
# returns an exportlist
sub parse_symset {
    my ($file) = @_;
    my @res;

    open(my $fh, '<', $file) or die "Error opening $file: $!\n";
    while (<$fh>) {
        my @l = split(/\s+/);
        if (@l < 4) {
            print STDERR "$file:$.: unknown line\n";
            next;
        }
        $l[0] =~ s/^0x//;
        push(@res, {crc => $l[0], sym => $l[1], mod => $l[2], type => $l[3]});
    }
    close($fh);
    return @res;
}

# greps an exportlist  for built-in symbols
sub builtin_exports {
    return grep { $_->{mod} =~ /(^vmlinux$)|(\/built-in$)/ } @_;
}

my %export_types = (
    __ksymtab            => "EXPORT_SYMBOL",
    __ksymtab_unused     => "EXPORT_UNUSED_SYMBOL",
    __ksymtab_gpl        => "EXPORT_SYMBOL_GPL",
    __ksymtab_unused_gpl => "EXPORT_UNUSED_SYMBOL_GPL",
    __ksymtab_gpl_future => "EXPORT_SYMBOL_GPL_FUTURE"
);
# returns an exportlist for a given module
sub module_exports {
    my ($file) = @_;
    my (%crcs, %types, @res);
    my $mod = $file;
    $mod =~ s/.*\/lib\/modules\/[^\/]*\/kernel\///;
    $mod =~ s/\.(k?o|a)$//;
    
    open(my $pipe, '-|', 'objdump', '-t', $file) or die "objdump -t $file: $!\n";
    while (<$pipe>) {
        my $l = $_;
        my @l = split(/\s+/);
        next if (@l < 3);
        next if ($l =~ /^[^ ]* .....d/); # debug symbol
        my $sym = $l[$#l];
        my $sec = $l[$#l - 2];
        if ($sym =~ /^__crc_(.*)/) {
            $crcs{$1} = $l[0];
            $crcs{$1} =~ s/^0{8}//;
        } elsif ($sym =~ /^__ksymtab_(.*)/ && exists($export_types{$sec})) {
            $types{$1} = $export_types{$sec};
        }
    }
    close($pipe);
    if ($? != 0) {
        die "objdump returned an error\n";
    }
    for my $sym (keys(%types)) {
        push(@res, {sym => $sym, crc => $crcs{$sym} || "0"x8, mod => $mod,
            type => $types{$sym}});
    }
    return @res;
}

# format an exportlist for output
sub format_exports {
    my $res = "";
    for my $exp (sort { $a->{sym} cmp $b->{sym} } @_) {
        $res .= "0x$exp->{crc}\t$exp->{sym}\t$exp->{mod}\t$exp->{type}\n";
    }
    return $res;
}

# splits exports by directories, returns a symsetlist
sub split_into_symsets {
    my %sets;

    for my $exp (@_) {
        my $set = $exp->{mod};
        $set =~ s/\/[^\/]+$//;
        $set =~ s/\//_/g;
        $sets{$set} ||= [];
        push(@{$sets{$set}}, $exp);
    }
    return map { [$_, $sets{$_}] } keys(%sets)
}

# loads symsets from a directory created by write_symsets
# returns symsetlist
# FIXME: multiple versions of a symset
sub load_symsets {
    my ($dir) = @_;
    my @sets;

    opendir(my $dh, $dir) or die "Error reading directory $dir: $!\n";
    for my $file (readdir($dh)) {
        next if $file =~ /^\.\.?$/;
        if (!-f "$dir/$file" || $file !~ /^(\w+)\.[0-9a-f]{16}$/) {
            print STDERR "Ignoring unknown file $dir/$file\n";
            next;
        }
        my $set = $1;
        push(@sets, [$set, [parse_symset("$dir/$file")]]);
    }
    closedir($dh);
    return @sets;
}

sub hash {
    return substr(md5_hex(@_), 0, 16);
}

# writes symsets as returned by split_into_symsets/load_symsets into $dir
sub write_symsets {
    my $dir = shift;
    my @sets = @_;

    my $print_only = (!defined($dir));
    for my $set (@sets) {
        my $name = $set->[0];
        my $exports = $set->[1];
        my $data = format_exports(@$exports);
        my $hash = hash($data);
        if ($print_only) {
            print "$name.$hash\n";
        } else {
            my $f = "$dir/$name.$hash";
            open(my $fh, '>', $f) or die "error creating $f: $!\n";
            print $fh $data;
            close($fh);
        }
    }
}

# loads kabi check configurations into %commonsyms, %usedsyms and %severities
sub load_kabi_files {
    my ($csfile, $usfile, $sevfile) = @_;

    if (defined($csfile)) {
        open(my $fh, '<', $csfile) or die "Can't open $csfile: $!\n";
        %commonsyms = map { s/\s+//g; ; $_ => 1 } <$fh>;
        close($fh);
    }
    if (defined($usfile)) {
        open(my $fh, '<', $usfile) or die "Can't open $usfile: $!\n";
        %usedsyms = map { s/\s+//g; $_ => 1 } <$fh>;
        close($fh);
    }
    if (defined($sevfile)) {
        open(my $fh, '<', $sevfile) or die "Can't open $sevfile: $!\n";
        while (<$fh>) {
            chomp;
            s/#.*//;
            next if /^\s*$/;
            my @f = split(/\s+/);
            if (@f != 2) {
                print STDERR "$sevfile:$.: unknown line\n";
                next;
            }
            if ($f[1] !~ /^\d+$/) {
                print STDERR "$sevfile:$.: invalid severity $f[1]\n";
                next;
            }
            # simple glob -> regexp conversion
            $f[0] =~ s/\*/.*/g;
            $f[0] =~ s/\?/./g;
            $f[0] =~ s/.*/^$&\$/;
            push(@severities, [@f]);
        }
        close($fh);
    }
}

# record kabi changes
sub kabi_change {
    my $exp = shift;
    my $sev;

    return if !$opt_check_kabi;

    $sev = 8;
    for my $rule (@severities) {
        if ($exp->{mod} =~ $rule->[0]) {
            $sev = $rule->[1];
            last;
        }
    }
    if (exists($usedsyms{$exp->{sym}})) {
        $sev += 16;
    } elsif (exists($commonsyms{$exp->{sym}})) {
        $sev += 8;
    }
    print STDERR "KABI: symbol $exp->{sym}.$exp->{crc} (badness $sev): @_\n";
    $kabi_badness = $sev if ($sev > $kabi_badness);
}

# check if all symbols from $old symsetlist are provided by $new symsetlist,
# add compatible symsets to $new
sub preserve_symsets {
    my ($old, $new) = @_;
    my (%symcrcs, %symsethashes);

    for my $set (@$new) {
        my $name = $set->[0];
        my $exports = $set->[1];
        $symsethashes{$name} = hash(format_exports(@$exports));
        for my $exp (@$exports) {
            $symcrcs{$exp->{sym}} = $exp->{crc};
        }
    }
    for my $set (@$old) {
        my $name = $set->[0];
        my $exports = $set->[1];
        my $hash = hash(format_exports(@$exports));
        if (exists($symsethashes{$name}) && $symsethashes{$name} eq $hash) {
            next;
        }
        my $compatible = 1;
        for my $exp (@$exports) {
            if (!exists($symcrcs{$exp->{sym}})) {
                kabi_change($exp, "missing");
                $compatible = 0;
                next;
            }
            if ($symcrcs{$exp->{sym}} ne $exp->{crc}) {
                kabi_change($exp, "crc changed to $symcrcs{$exp->{sym}}\n");
                $compatible = 0;
            }
        }
        if ($compatible) {
            print STDERR "KABI: symset $name.$hash preserved\n" if $opt_verbose;
            push(@$new, $set);
        } else {
            print STDERR "KABI: symset $name.$hash is NOT preserved\n" if $opt_verbose;
        }
    }
}


main();

# vim: sw=4:et:sts=4
