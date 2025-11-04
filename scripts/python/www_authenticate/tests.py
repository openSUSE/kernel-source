import itertools
import unittest

import www_authenticate

challenges = (
    ('Negotiate',
     ('negotiate', None)),
    ('Negotiate abcdef',
     ('negotiate', 'abcdef')),
    ('Negotiate abcdef=',
     ('negotiate', 'abcdef=')),
    ('Negotiate abcdef==',
     ('negotiate', 'abcdef==')),
    ('Bearer realm=example.com',
     ('bearer', {'realm': 'example.com'})),
    ('Bearer realm="example.com"',
     ('bearer', {'realm': 'example.com'})),
    ('Digest realm="example.com", qop="auth,auth-int", nonce="abcdef", opaque="ghijkl"',
     ('digest', {'realm': 'example.com', 'qop': 'auth,auth-int', 'nonce': 'abcdef', 'opaque': 'ghijkl'})),
)


class ParseTestCase(unittest.TestCase):
    def testValid(self):
        for r in range(1, len(challenges) + 1):
            for permutation in itertools.permutations(challenges, r):
                # Skip those that have the same authentication scheme more than once.
                if len(set(challenge[1][0] for challenge in permutation)) != len(permutation):
                    continue
                # Skip any permutation that contains a Negotiate challenge
                # with a token, if it's not the only challenge.
                if len(permutation) > 1 and \
                   any(challenge[1][0] == 'negotiate' and challenge[1][1] != None
                       for challenge in permutation):
                    continue
                full_challenge = ', '.join(challenge[0] for challenge in permutation)
                print(full_challenge)
                parsed = www_authenticate.parse(full_challenge)
                for left, right in zip(permutation, parsed):
                    self.assertEqual(left[1][0], right)
                    self.assertEqual(left[1][1], parsed[right])

