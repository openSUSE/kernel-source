package List::Flatten;

use warnings;
use strict;

require Exporter;
use base qw(Exporter);
our @EXPORT = qw(flat);


=head1 NAME

List::Flatten - Interpolate array references in a list


=head1 VERSION

Version 0.01

=cut

our $VERSION = '0.01';


=head1 SYNOPSIS

    use List::Flatten;

    my @foo = (1, 2, [3, 4, 5], 6, [7, 8], 9);
    # @foo contains 6 elements, 2 of them are array references
    
    my @bar = flat @foo;
    # @bar contains 9 elements, same as (1 .. 9)


=head1 EXPORT

Exports the only function B<flat> by default.


=head1 FUNCTIONS

=head2 flat

B<Arguments:> a list of arbitrary values, parantheses for B<flat> are optional.

B<Returns:> the same list, except that the values of any array references are interpolated into the
list. Does not work recursively!

=cut

sub flat(@) {
	return map { ref eq 'ARRAY' ? @$_ : $_ } @_;
}


=head1 AUTHOR

Darko Obradovic, C<< <dobradovic at gmx.de> >>


=head1 BUGS

Please report any bugs or feature requests to C<bug-list-flatten at rt.cpan.org>, or through
the web interface at L<http://rt.cpan.org/NoAuth/ReportBug.html?Queue=List-Flatten>.  I will be notified, and then you'll
automatically be notified of progress on your bug as I make changes.


=head1 SUPPORT

You can find documentation for this module with the perldoc command.

    perldoc List::Flatten


You can also look for information at:

=over 4

=item * RT: CPAN's request tracker

L<http://rt.cpan.org/NoAuth/Bugs.html?Dist=List-Flatten>

=item * AnnoCPAN: Annotated CPAN documentation

L<http://annocpan.org/dist/List-Flatten>

=item * CPAN Ratings

L<http://cpanratings.perl.org/d/List-Flatten>

=item * Search CPAN

L<http://search.cpan.org/dist/List-Flatten>

=back


=head1 COPYRIGHT & LICENSE

Copyright 2009 Darko Obradovic, all rights reserved.

This program is free software; you can redistribute it and/or modify it
under the same terms as Perl itself.

=cut

1;
