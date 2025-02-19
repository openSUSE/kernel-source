package SUSE::MyBS;

use strict;
use warnings;

use Carp;
use LWP::UserAgent;
use URI;
use XML::Parser;
use XML::Writer;
use HTTP::Request;
use File::Temp qw(tempfile);
use File::Copy qw(move);
use File::Basename;
use File::Path qw/make_path/;
use Config::IniFiles;
use Digest::MD5;
use IPC::Open2;
use MIME::Base64;
use Fcntl;
use POSIX qw(strftime);
use Errno;

use SUSE::MyBS::Buildresults;

my $cookiefile = "~/.local/state/MyBS/cookie";
my $lockfile = $cookiefile . ".lock";
my $locktime = 300;
my $errok = ();

sub new {
	my ($class, $api_url) = @_;
	my $self = { };

	$api_url ||= "https://api.opensuse.org";
	$api_url =~ s:/*$::;
	if ($api_url !~ m@^https?://@) {
		$api_url = "https://$api_url";
	}
	$self->{url} = URI->new($api_url);

	my $cfgfile;
	foreach ("$ENV{HOME}/.oscrc", "$ENV{HOME}/.config/osc/oscrc") {
		if (-f) {
			$cfgfile = $_;
			last;
		}
	}

	defined $cfgfile or die "oscrc not found";

	# replace name: value with name= value that Config::IniFiles can parse
	open(my $fh, '<', $cfgfile) or die "$cfgfile: $!\n";
	my $data = "";
	my $changed = 0;
	while (<$fh>) {
		if (s/^([^[:=]+):/$1=/) {
			$changed = 1;
		}
		$data .= $_;
	}
	close($fh);
	my $config;
	if ($changed) {
		(my $fh, $cfgfile) = tempfile();
		print $fh $data;
		close($fh);
	}
	my %config;
	tie %config, 'Config::IniFiles', (-file => $cfgfile);
	if ($changed) {
		unlink($cfgfile);
	}
	if (!keys(%config)) {
		die join("\n", @Config::IniFiles::errors), "\n";
	}
	my %cred;
	for my $kw (qw(user pass passx sshkey keyring gnome_keyring credentials_mgr_class)) {
		for my $section ($api_url, "$api_url/", $self->{url}->host) {
			if (exists($config{$section}) &&
					exists($config{$section}{$kw})) {
				$cred{$kw} = $config{$section}{$kw};
				last;
			}
		}
	}
	if (exists($cred{sshkey})) {
		my $sshkey = $cred{sshkey};
		my $home = $ENV{'HOME'} . "/";

		$sshkey =~ s,^~[/],$home,;
		$sshkey="~/.ssh/" . $sshkey unless $sshkey =~ /^\//;
		$sshkey =~ s,^~[/],$home,;
		die "Cannot access SSH key file $sshkey\n" unless -r $sshkey;
		$self->{sshkey} = $sshkey;
		$self->{user} = $cred{user};
		if ( -x "/usr/lib/osc/ssh-keygen") {
			print STDERR "Using OBS keygen in /usr/lib/osc/ssh-keygen\n";
			$self->{keygen} = "/usr/lib/osc/ssh-keygen";
		} else {
			$self->{keygen} = "ssh-keygen";
		}
	} else {
		if (exists($cred{credentials_mgr_class})) {
			if ($cred{credentials_mgr_class} eq "osc.credentials.ObfuscatedConfigFileCredentialsManager") {
				$cred{passx}=$cred{pass};
			} elsif ($cred{credentials_mgr_class} eq "osc.credentials.KeyringCredentialsManager:pass.Keyring") {
				# emulate by invoking the pass command directly
				my $api = $api_url;
				$api =~ s/^https?:\/\///;
				open(my $secret, "pass show $api/$cred{user} |")
					or die "Failed to invoke pass\n";
				$cred{pass} = <$secret>;
				close($secret);
				die "Failed to obtain secret from pass\n"
				if !$cred{pass};
				chomp($cred{pass});
			}
		}
		if (exists($cred{passx})) {
			# Not available on SLES10, hence the 'require'
			require MIME::Base64;
			require IO::Uncompress::Bunzip2;
			my $bz2 = MIME::Base64::decode_base64($cred{passx});
			$cred{pass} = "";
			IO::Uncompress::Bunzip2::bunzip2(\$bz2 => \$cred{pass})
				or die "Decoding password for $api_url failed: $IO::Uncompress::Bunzip2::Bunzip2Error\n";
		}
		if (!exists($cred{pass}) && ((exists($cred{keyring}) || exists($cred{gnome_keyring}))
						|| exists($cred{credentials_mgr_class}) &&
						$cred{credentials_mgr_class} eq "osc.credentials.KeyringCredentialsManager:keyring.backends.SecretService.Keyring")) {
			my $api = $api_url;
			$api =~ s/^https?:\/\///;
			open(my $secret, "secret-tool lookup service $api username $cred{user} |")
				or die "Please install the \"secret-tool\" package to use a keyring\n";
			$cred{pass} = <$secret>;
			close($secret);
			die "Failed to obtain secret from secret-tool\n"
			if !$cred{pass};
			chomp($cred{pass});
		}
	}
	if (!exists($cred{user}) || (!exists($cred{pass}) && !exists($cred{sshkey}))) {
		die "Error: Username or password for $api_url not set in ~/.oscrc\n" .
		"Error: Run `osc -A $api_url ls' once\n";
	}

	$self->{ua} = LWP::UserAgent->new;
	my $realm = "Use your developer account";
	$realm = "Use your SUSE developer account" if $api_url =~ /opensuse/;
	if (exists($self->{sshkey})) {
		$self->{realm} = $realm;
	} else {
		$self->{ua}->credentials($self->{url}->host_port, $realm,
			$cred{user}, $cred{pass});
	}
	if ($self->{ua}->can('ssl_opts')) {
		$self->{ua}->ssl_opts(verify_hostname => 1);
	}

	bless($self, $class);

	$self->load_cookie();

	if ($self->{url}->scheme eq "https" &&
				$self->{url}->host eq "api.suse.de" &&
				$self->{ua}->can('ssl_opts')) {
		eval {
			$self->get("/about");
		};
		if ($@) {
			my $error = $@;
			if ($@ =~ /certificate verify failed/) {
				$self->unlock_cookie();
				# Use the canned certificate as a backup
				# XXX: Check that we really got an unknown cert error
				(my $pkg = __PACKAGE__) =~ s@::@/@g;
				$pkg .= ".pm";
				(my $cert = $INC{$pkg}) =~ s@[^/]*$@@;
				$cert .= "SUSE_Trust_Root.pem";
				$self->{ua}->ssl_opts(SSL_ca_file => $cert);
			} else {
				die $error;
			}
		}
	}
	return $self;
}

sub check_cookie {
	my $self = $_[0];
	my ($dev,$ino,$mode,$nlink,$uid,$gid,$rdev,$size,$atime,$mtime,$ctime,$blksize,$blocks) = stat($cookiefile);
	# printf("Loaded cookie from %s, current cookie time is %s\n", $self->{cookietime} ? $self->{cookietime} : 'none', $mtime ? $mtime : 'none');
	if ($mtime && (!$self->{cookietime} || ($self->{cookietime} < $mtime))) {
		$self->load_cookie();
		return 1;
	}
	return undef;
}

sub load_cookie {
	my $self = $_[0];
	my $home = $ENV{'HOME'} . "/";
	$cookiefile =~ s,^~[/],$home,;
	my ($dev,$ino,$mode,$nlink,$uid,$gid,$rdev,$size,$atime,$mtime,$ctime,$blksize,$blocks) = stat($cookiefile);
	$self->{cookietime} = $mtime;
	if (-r $cookiefile) {
		my $cookie = do {
			open(my $fh, $cookiefile);
			local $/ = undef;
			<$fh>;
		};
		# print "Loading ";
		$self->process_cookie($cookie);
	}
}

sub process_cookie {
	my ($self, $cookie) = @_;
	my @cookie = split /\s*([^=;]+)\s*=\s*([^=;]+)\s*;?/, $cookie;
	# print "Cookie: $cookie[1]=$cookie[2]\n";
	$self->{cookies}{$cookie[1]} = $cookie[2];
}

sub open_cookie {
	my $self = $_[0];
	my $home = $ENV{'HOME'} . "/";
	$lockfile =~ s,^~[/],$home,;
	my $dir = dirname($lockfile);
	make_path($dir);
	my $fh, my $filename;
	my $ret = sysopen $fh, $lockfile, O_CREAT|O_EXCL|O_WRONLY, 0644;
	if ($ret) {
		($fh, $filename) = tempfile( 'cookie-XXXXXX', DIR => $dir);
	} else {
		if (!$!{EEXIST}) {
			die "Cannot access $lockfile: $!\n";
		}
	}
	return undef unless $ret;
	$self->{lock} = $fh;
	$self->{cookiefile} = $filename;
	return $fh;
}

sub lock_cookie {
	my $self = $_[0];
	die "Deadlock: Already locked!\n" if $self->{lock};
	my $ret = $self->open_cookie();
	my $delay = 1;
	while (!$ret) {
		my ($dev,$ino,$mode,$nlink,$uid,$gid,$rdev,$size,$atime,$mtime,$ctime,$blksize,$blocks) = stat($lockfile);
		if ($mtime) {
			my $age = time() - $mtime;
			my $remain = $locktime - $age;
			if ($remain > 0) {
				sleep((($remain > 0) && ($remain < $delay)) ? $remain : $delay);
				$delay *= 2;
			} else {
				my $date = strftime("%F %R", localtime($mtime));
				print STDERR "Cookie file $cookiefile locked for $age seconds since $date\n";
				unlink "$lockfile";
			}
		} else {
			if (!$!{ENOENT}) {
				die "Cannot access $lockfile: $!\n";
			}
			$ret = $self->open_cookie();
		}
	}
}

sub DESTROY {
	my $self = $_[0];

	$self->unlock_cookie();
}

sub unlock_cookie {
	my $self = $_[0];

	if ($self->{lock}) {
		unlink($lockfile, $self->{cookiefile});
		$self->{lock} = undef;
		$self->{cookiefile} = undef;
	}
}

sub save_cookie {
	my ($self, $cookie) = @_;
	my $fh = $self->{lock};

	if ($fh) {
		print $fh $cookie;

		close($fh);

		move($self->{cookiefile}, $cookiefile);
		unlink($lockfile);

		$self->{lock} = undef;
		$self->{cookiefile} = undef;
	}
}

sub ssh_auth {
	my $self = $_[0];
	my $now = time();
	my $key = $self->{sshkey};
	my $realm = $self->{realm};
	my $user = $self->{user};
	my $data = "(created): $now";
	my $keygen = $self->{keygen};

	my $pid = open2(my $reader, my $writer, $keygen, '-Y', 'sign', '-f', $key, '-n', $realm, '-q');
	print $writer $data;
	close $writer;
	my $sig = do {
		local $/ = undef;
		<$reader>;
	};
	die "Failed to get SSH signature.\n" unless $sig =~ /\A-----BEGIN SSH SIGNATURE-----\n\K.*(?=\n-----END SSH SIGNATURE-----\Z)/ms;
	$sig = $&;
	$sig = encode_base64(decode_base64($sig), '');
	$sig = "keyId=\"$user\",algorithm=\"ssh\",headers=\"(created)\",created=$now,signature=\"$sig\"";
	$sig = "Signature $sig";

	waitpid $pid, 0;

	return $sig;
}

sub api {
	my ($self, $method, $path, $data) = @_;
	my $url = $self->{url} . $path;

	my $req = HTTP::Request->new($method => $url);
	my $cookies = $self->{cookies};
	if (keys % { $cookies } ) {
		my @cookies = ();
		foreach my $cookie (keys % { $cookies } ) {
			@cookies = (@cookies, "$cookie=" . $cookies->{$cookie});
		}
		my $cookies = join("; ", @cookies);
		# print "Cookies: $cookies\n";
		$req->header("Cookie" => $cookies);
	} else {
		if (exists($self->{sshkey})) {
			$self->lock_cookie();
			$req->header("Authorization", $self->ssh_auth()) unless $self->check_cookie();
		}
	}
	if ($data) {
		$req->add_content($data);
		$req->header("Content-type" => "application/octet-stream");
	}
	#$self->{ua}->prepare_request($req);
	#print STDERR "req: " . $req->as_string() . "\n";
	#$self->{ua}->add_handler(request_send => sub { my($req, $ua, $handler) = @_; print STDERR "req: " . $req->as_string() . "\n"; return; m_method => "GET"});
	my $res = $self->{ua}->request($req);
	if (($res->code == 401) && (keys % { $cookies } ) && exists($self->{sshkey})) {
		$self->lock_cookie();
		$req->header("Authorization", $self->ssh_auth()) unless $self->check_cookie();
		$res = $self->{ua}->request($req);
	}
	if ($res->code != 200) {
		#print STDERR $res->as_string();
		my $message = "$method $path: @{[$res->message()]} (HTTP @{[$res->code()]})\n";
		if ($errok) {
			print STDERR $message;
		} else {
			die $message;
		}
	}
	my $headers = $res->headers();
	my $cookie = $headers->{'set-cookie'};
	if ($cookie) {
		$self->process_cookie($cookie);
		$self->save_cookie($cookie);
	}

	return $res->content();
}

sub get {
	my $self = shift;

	$self->api('GET', @_);
}

sub post {
	my $self = shift;

	$self->api('POST', @_);
}

sub put {
	my $self = shift;

	$self->api('PUT', @_);
}

sub put_file {
	my ($self, $file, $path) = @_;

	open(my $fh, '<', $file) or die "$file: $!\n";
	local $/ = undef;
	my $data = <$fh>;
	close($fh);
	$self->put($path, $data);
}

sub delete {
	my $self = shift;

	$self->api('DELETE', @_);
}

sub exists {
	my ($self, $path) = @_;

	eval {
		$self->get($path);
	};
	return 0 if $@;
	return 1;
}

sub project_exists {
	my ($self, $project) = @_;

	return $self->exists("/source/$project/_meta");
}

sub package_exists {
	my ($self, $project, $package) = @_;

	return $self->exists("/source/$project/$package/_meta");
}

sub readdir {
	my ($self, $path) = @_;
	my $xml = $self->get($path);

	my $handle_start = sub  {
		my ($self, $element, %attr) = @_;
		return unless $element eq "entry" || $element eq "binary";
		my $name;
		if ($attr{name}) {
			$name = $attr{name};
			delete($attr{name});
		} elsif ($attr{filename}) {
			$name = $attr{filename};
			delete($attr{filename});
		}
		$self->{res}->{$name} = \%attr;
	};

	my $p = XML::Parser->new(Handlers => {Start => $handle_start});
	$p->{res} = {};
	$p->parse($xml);
	return $p->{res};
}

# Return list of architectures for given repository of given project
sub get_repo_archs {
	my ($self, $project, $repository) = @_;
	my $xml = $self->get("/source/$project/_meta");

	my $handle_start = sub  {
		my ($self, $element, %attr) = @_;

		return if $element ne "repository";
		if (defined($repository)) {
			return if $attr{name} ne $repository;
		}
		if ($attr{name} eq "standard" || $attr{name} eq "pool" ||
		    $attr{name} eq "ports" && $project !~ /\bopenSUSE:Factory\b/ && $project !~ /\bALP\b/ && $project !~ /\bSLFO\b/ ||
		    $attr{name} =~ /^SUSE_.*_Update$/ && $project =~ /^SUSE:Maintenance:/) {
			$self->{has_match} = 1;
			$self->{repo_name} = $attr{name};
			$self->{res}{$attr{name}} ||= [];
		}
	};
	my $handle_char = sub {
		my ($self, $string) = @_;

		if ($self->{has_match}) {
			$string =~ s/\s//g;
			$self->{cur_string} .= $string;
		}
	};
	my $handle_end = sub {
		my ($self, $element) = @_;

		if ($element eq "repository") {
			$self->{has_match} = 0;
		}
		if ($element eq "arch" && $self->{has_match}) {
			# i586 in openSUSE:Factory is excluded from builds
			if ($project !~ '^(openSUSE.org:)?openSUSE:Factory$' || $self->{cur_string} ne 'i586') {
				push(@{$self->{res}{$self->{repo_name}}}, $self->{cur_string});
			}
			$self->{cur_string} = "";
		}
	};
	my $p = XML::Parser->new(Handlers => {
			Start => $handle_start,
			Char => $handle_char,
			End => $handle_end});
	$p->{res} = {};
	$p->parse($xml);
	return %{$p->{res}};
}

sub create_project {
	my ($self, $project, $options) = @_;
	my $multibuild = $options->{multibuild};
	my %limit_archs;

	$options->{title} ||= $project,
	$options->{description} ||= "";
	if (!exists($options->{build})) {
		$options->{build} = 1;
	}
	if (!exists($options->{publish})) {
		$options->{publish} = 1;
	}
	$options->{limit_archs} ||= [];
	if (scalar(@{$options->{limit_archs}})) {
		$limit_archs{$_} = 1 for @{$options->{limit_archs}};
	} else {
		$options->{limit_archs} = undef;
	}

	my $meta;
	my $writer = XML::Writer->new(OUTPUT => \$meta);
	$writer->startTag("project", name => $project);
	$writer->dataElement("title", $options->{title});
	$writer->dataElement("description", $options->{description});
	$options->{maintainers} ||= [];
	for my $m (@{$options->{maintainers}}) {
		if ($self->exists("/group/$m")) {
			$writer->emptyTag("group", groupid => $m,
				role => "maintainer");
		} elsif ($self->exists("/person/$m")) {
			$writer->emptyTag("person", userid => $m,
				role => "maintainer");
		} else {
			warn("User id $m does not exist at $self->{url}\n");
		}
	}

	if (!exists($options->{repos})) {
		if (!exists($options->{base})) {
			croak "Either 'base' or 'repos' must be specified";
		}
		$options->{repository} ||= "";
		$options->{repos} = { $options->{repository} => $options->{base} };
	}
	my %seen_archs;
	my @qa_repos;
	for my $repo (sort(keys(%{$options->{repos}}))) {
		my $base = $options->{repos}{$repo};
		my %repo_archs;
		if ($repo eq "") {
			# get all "default" repositories of a given project
			%repo_archs = $self->get_repo_archs($base);
		} else {
			# get the "standard" repository of a given project
			%repo_archs = $self->get_repo_archs($base, "standard");
		}
		for my $r (sort(keys(%repo_archs))) {
			my $name = $repo ? $repo : $r;
			my @attrs = (name => $name);
			if (!$options->{rebuild}) {
				push(@attrs, rebuild => "local", block => "local");
			}
			my @archs;
			for my $arch (@{$repo_archs{$r}}) {
				if ($options->{limit_archs} &&
					!$limit_archs{$arch}) {
					next;
				}
				# only build each arch once
				if ($seen_archs{$arch}) {
					next;
				}
				$seen_archs{$arch} = 1;
				push(@archs, $arch);
			}
			if (!@archs) {
				# this repository is not needed
				next;
			}
			$writer->startTag("repository", @attrs);
			$writer->emptyTag("path", repository => $r,
				project => $base);
			for my $arch (@archs) {
				$writer->dataElement("arch", $arch);
			}
			$writer->endTag("repository");
			if (!exists($options->{qa})) {
				next;
			}
			# For each regular repository foo, there is a
			# repository named QA_foo, building against foo
			my $qa_name = (($name eq "standard") || ($name eq "pool")) ? "QA"
					: "QA_$name";
			$writer->startTag("repository", name => $qa_name);
			$writer->emptyTag("path", repository => $name,
				project => $project);
			for my $arch (@archs) {
				$writer->dataElement("arch", $arch);
			}
			$writer->endTag("repository");
			push(@qa_repos, $qa_name);
		}
	}
	for my $attr (qw(build publish debuginfo)) {
		$writer->startTag($attr);
		$writer->emptyTag($options->{$attr} ? "enable" : "disable");
		if ($attr =~ /^(publish|build)/) {
			for my $repo (@qa_repos) {
				$writer->emptyTag("disable", repository => $repo);
			}
		}
		$writer->endTag($attr);
	}

	$writer->endTag("project");
	$writer->end();

	$self->put("/source/$project/_meta?force=1", $meta);
	my $prjconf = "";
	if ($options->{prjconf}) {
		$prjconf .= $options->{prjconf};
	}
	for my $package (@{$options->{remove_packages} || []}) {
		# OBS idiom: substitute the package by an empty set
		$prjconf .= "Substitute: $package\n";
	}
	for my $package (@{$options->{add_packages} || []}) {
		$prjconf .= "Support: $package\n";
	}
	$prjconf .= "Macros:\n";
	for my $macro (@{$options->{macros} || []}) {
		$prjconf .= "$macro\n";
	}
	my $qa_expr = "";
	for my $repo (@qa_repos) {
		my $separator = $qa_expr ? " || " : "";
		$qa_expr .= $separator . '("%_repository" == "' . $repo . '")';
	}
	$prjconf .= "%is_kotd_qa ($qa_expr)\n";
	$prjconf .= ":Macros\n";
	my $specfiles = $options->{limit_packages} || [];
	if (@$specfiles && $multibuild) {
		my %specfiles = map { $_ => 1 } @$specfiles;
		my $package = $options->{package};
		for my $spec (keys(%specfiles)) {
			$spec = ($spec eq $package) ? $package : "$package:$spec";
			$prjconf .= "BuildFlags: onlybuild:$spec\n";
		}
	}
	$self->put("/source/$project/_config", $prjconf);
	return { name => $project, qa_repos => \@qa_repos };
}

sub create_package {
	my ($self, $prj, $package, $qa_package, $qa_std_package) = @_;

	my $meta;
	my $writer = XML::Writer->new(OUTPUT => \$meta);
	$writer->startTag("package", project => $prj->{name}, name => $package);
	$writer->dataElement("title", $package);
	$writer->dataElement("description", "");
	if ($qa_package) {
		$writer->startTag("build");
		$writer->emptyTag("disable") unless $qa_std_package;
		for my $repo (@{$prj->{qa_repos} || []}) {
			$writer->emptyTag("enable", repository => $repo);
		}
		$writer->endTag("build");
	}
	$writer->endTag("package");
	$writer->end();

	$self->put("/source/$prj->{name}/$package/_meta", $meta);
}

# Get a list of links to this package within the same project
sub local_links {
	my ($self, $project, $package) = @_;

	my $xml = $self->post("/source/$project/$package?cmd=showlinked");

	my $handle_start = sub  {
		my ($self, $element, %attr) = @_;
		return unless $element eq "package";
		return unless exists($attr{project}) && exists($attr{name});
		if ($attr{project} eq $project && $attr{name} ne $package) {
			push(@{$self->{res}}, $attr{name});
		}
	};

	my $p = XML::Parser->new(Handlers => {Start => $handle_start});
	$p->{res} = [];
	$p->parse($xml);
	return @{$p->{res}};
}

sub get_directory_revision {
	my ($self, $xml) = @_;

	my $handle_start = sub {
		my ($self, $element, %attr) = @_;
		return unless $element eq "directory";
		$self->{res}[0] = $attr{rev};
	};
	my $p = XML::Parser->new(Handlers => {Start => $handle_start});
	$p->{res} = [];
	$p->parse($xml);
	return $p->{res}[0];
}

sub wipe_package {
	my ($self, $project, $package, $progresscb) = @_;
	$errok = 1;
	$self->post("/build/$project?cmd=wipe&package=$package");
	$errok = ();
	&$progresscb('WIPE', "$project/$package");
}

sub upload_package {
	my ($self, $dir, $prj, $package, $commit, $options) = @_;
	$options ||= {};
	my $multibuild = $options->{multibuild};
	my $progresscb = $options->{progresscb} || sub { };
	my $no_init = $options->{no_init};
	my $remove_packages = $options->{remove_packages} || [];
	my %remove_packages = map { $_ => 1 } @$remove_packages;
	my $specfiles = $options->{specfiles} || [];
	my %specfiles = map { $_ => 1 } @$specfiles;
	my $revision;
	if (!ref($prj)) {
		$prj = { name => $prj };
	}
	my $project = $prj->{name};

	if (!$self->project_exists($project)) {
		die "Project $project does not exist\n";
	}
	if (!$no_init) {
		$self->create_package($prj, $package, $multibuild, 1);
		&$progresscb('CREATE', "$project/$package");
	}
	# delete stale kernel-obs-build
	my $wipe = 'kernel-obs-build';
	if (($specfiles{$wipe} or $multibuild) and not $no_init) {
		$wipe = ($multibuild ? $package . ":" : "") . $wipe;
		$self->wipe_package($project, $wipe, $progresscb);
	} else {
		$wipe = ();
	}
	opendir(my $dh, $dir) or die "$dir: $!\n";
	my $remote = $self->readdir("/source/$project/$package");
	my $new_filelist = "";
	my $filelist_writer = XML::Writer->new(OUTPUT => \$new_filelist);
	$filelist_writer->startTag("directory");
	my $changed = 0;
	while ((my $name = CORE::readdir($dh))) {
		my $local_path = "$dir/$name";
		my $remote_path = "/source/$project/$package/$name?rev=repository";
		next if $name =~ /^\./;
		next if ! -f $local_path;
		open(my $fh, '<', "$dir/$name") or die "$dir/$name: $!\n";
		my $md5 = Digest::MD5->new->addfile($fh)->hexdigest;
		$filelist_writer->emptyTag("entry", name => $name, md5 => $md5);
		if (!$remote->{$name} || $md5 ne $remote->{$name}->{md5}) {
			$self->put_file($local_path, $remote_path);
			&$progresscb('PUT', $name);
			$changed = 1;
		}
		if ($remote->{$name}) {
			delete $remote->{$name};
		}
	}
	closedir($dh);
	for my $name (keys(%$remote)) {
		$self->delete("/source/$project/$package/$name");
		&$progresscb('DELETE', $name);
		$changed = 1;
	}
	$filelist_writer->endTag("directory");
	$filelist_writer->end();
	if ($changed) {
		my $xml = $self->post("/source/$project/$package?comment=$commit&cmd=commitfilelist", $new_filelist);
		$revision = $self->get_directory_revision($xml);
	}
	if ($no_init) {
		return $revision;
	}

	# Create links for all specfiles in this package
	my %links = map { $_ => 1 } $self->local_links($project, $package);
	if (not $multibuild) {
		my $link_xml;
		my $writer = XML::Writer->new(OUTPUT => \$link_xml);
		$writer->emptyTag("link", project => $project, package => $package,
			cicount => "copy");
		$writer->end();
		for my $spec (keys(%specfiles)) {
			next if $remove_packages{$spec};
			next if $spec eq $package;
			$self->create_package($prj, $spec, ($spec =~ /^kernel-obs-(qa|build)/));
			$self->put("/source/$project/$spec/_link", $link_xml);
			&$progresscb('LINK', "$project/$spec");
			delete($links{$spec});
		}
	}
	# delete stale links
	for my $link (keys(%links)) {
		$self->delete("/source/$project/$link");
		&$progresscb('DELETE', "$project/$link");
	}
	# delete stale kernel-obs-build
	if ($wipe) {
		$self->wipe_package($project, $wipe, $progresscb);
	}
	return $revision;
}

sub submit_package {
	my ($self, $project, $package, $revision, $target, $comment) = @_;

	my $request;
	my $writer = XML::Writer->new(OUTPUT => \$request);
	$writer->startTag("request", type => "submit");
		$writer->startTag("submit");
			$writer->emptyTag("source",
				project => $project, package => $package,
				rev => $revision);
			$writer->emptyTag("target",
				project => $target, package => $package);
		$writer->endTag("submit");
		$writer->emptyTag("state", name => "new");
		$writer->dataElement("description", $comment);
	$writer->endTag("request");
	$writer->end();
	$self->post("/request?cmd=create", $request);
}

sub get_logfile {
	my ($self, $project, $package, $repository, $arch) = @_;

	$repository ||= "standard";
	return $self->get("/build/$project/$repository/$arch/$package/_log?nostream=1");
}

sub get_make_stderr {
	my ($self, $project, $package, $repository, $arch) = @_;

	$repository ||= "standard";
	return $self->get("/build/$project/$repository/$arch/$package/make-stderr.log");
}


sub get_kernel_commit {
	my ($self, $project, $package, $revision) = @_;

	my $content;
	for my $file (qw(source-timestamp build-source-timestamp)) {
		my $path = "/source/$project/$package/$file";
		$path .= "?rev=$revision" if $revision;
		eval {
			$content = $self->get($path);
		};
		last unless $@;
	}
	die "No timestamp file found in $project/$package\n" unless $content;
	if ($content !~ /^GIT Revision: ([0-9a-f]+)$/m) {
		die "Malformet timestamp file in $project/$package\n";
	}
	return $1;
}

sub get_results {
	my ($self, $project, $repository, $arch) = @_;

	my @params;
	push(@params, "repository=$repository") if $repository;
	push(@params, "arch=$arch") if $arch;
	my $xml = $self->get("/build/$project/_result?" . join("&", @params));
	return SUSE::MyBS::Buildresults->new($xml);
}

sub load_results {
	my ($self, $file) = @_;
	my $xml = "";

	local $/ = undef;
	if (open(my $fh, '<', $file)) {
		$xml = <$fh>;
	};
	return SUSE::MyBS::Buildresults->new($xml);
}

sub list_projects {
	my $self = shift;

	return keys(%{$self->readdir("/source")});
}

sub delete_project {
	my ($self, $project) = @_;

	return $self->delete("/source/$project?force=1");
}

1;
