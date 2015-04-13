package SUSE::MyBS::Buildresults;

use strict;
use warnings;

use XML::Parser;
use XML::Writer;
use IO::File;
use Data::Dumper;

sub new {
	my ($class, $xml) = @_;
	my $self = { };

	my $serial = "";
	my (%results, $cur_arch, $cur_repo);
	my $handle_start = sub {
		my ($self, $element, %attr) = @_;

		if ($element eq "resultlist") {
			if (!$attr{state}) {
				warn "Invalid result XML (state attribute missing)\n";
			}
			$serial = $attr{state};
		} elsif ($element eq "result") {
			$cur_arch = $attr{arch};
			$cur_repo = $attr{repository};
			$results{$cur_repo} ||= {};
			$results{$cur_repo}{$cur_arch} ||= {};
		} elsif ($element eq "status") {
			if (!$cur_arch || !$cur_repo) {
				warn "Invalid result XML (no arch set)\n";
				return
			}
			for my $a (qw(package code)) {
				if (!$attr{$a}) {
					warn "Invalid result XML ($a attribute missing)\n";
					return
				}
			}
			my $package = $attr{package};
			my $result = $attr{code};
			$results{$cur_repo}{$cur_arch}{$package}  = $result;
		}

	};
	if ($xml) {
		my $p = XML::Parser->new(Handlers => {Start => $handle_start});
		$p->parse($xml);
	}
	my @repos = sort(keys(%results));
	my %archs;
	my %packages;
	for my $repo (@repos) {
		for my $arch (keys(%{$results{$repo}})) {
			$archs{$arch} = 1;
			$packages{$_} = 1 for keys(%{$results{$repo}{$arch}});
		}

	}
	my @archs = sort(keys(%archs));
	my @packages = sort(keys(%packages));
	$self->{results} = \%results;
	$self->{repos} = \@repos;
	$self->{archs} = \@archs;
	$self->{packages} = \@packages;
	$self->{serial} = $serial;

	bless($self, $class);
	return $self;
}

sub save {
	my ($self, $file) = @_;

	my $out = IO::File->new($file, '>');
	my $writer = XML::Writer->new(OUTPUT => $out);
	$writer->startTag("resultlist", state => $self->{serial});
	for my $repo ($self->repos()) {
		for my $arch ($self->archs()) {
			next unless exists $self->{results}{$repo}{$arch};
			$writer->startTag("result", repository => $repo,
				arch => $arch);
			my @packages = keys(%{$self->{results}{$repo}{$arch}});
			for my $package (sort(@packages)) {
				my $code = $self->{results}{$repo}{$arch}{$package};
				$writer->emptyTag("status",
					package => $package,
					code => $code);
			}
			$writer->endTag("result");
		}
	}
	$writer->endTag("resultlist");
	$writer->end();
	$out->close();
}

sub serial {
	my $self = shift;

	return $self->{serial};
}

sub result {
	my ($self, $repo, $arch, $package) = @_;

	return unless exists $self->{results}{$repo};
	return unless exists $self->{results}{$repo}{$arch};
	return unless exists $self->{results}{$repo}{$arch}{$package};
	return $self->{results}{$repo}{$arch}{$package};
}

sub mark_broken {
	my ($self, $repo, $arch, $package) = @_;

	delete $self->{results}{$repo}{$arch}{$package};
	# This makes sure that the results will be evaluated again next time
	$self->{serial} = "broken";
}

sub repos {
	my $self = shift;

	return @{$self->{repos}};
}

sub archs {
	my $self = shift;

	return @{$self->{archs}};
}

sub packages {
	my $self = shift;

	return @{$self->{packages}};
}

sub dump {
	my $self = shift;

	print "serial: $self->{serial}\n";
	print Dumper($self->{results});
}

1;
