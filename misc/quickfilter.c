/** quickfilter.c
 *
 * Program takes a alphabetically sorted list of strings as arguments
 * and reads lines from stdin; the lines are echoed to stdout if the
 * first string in the line (separated by space, tab or newline) matches
 * one of the command line arguments.
 * Optional a flag -v inverts the results.
 *
 * Program replaces egrep but is a few orders of magnitude faster and
 * less memory consuming for this special task.
 * 
 * Limitations: 
 * - Strings need to 3 characters in length min
 * - Lines will be cut if longer than 255 characters
 *   
 * (c) Kurt Garloff <garloff@suse.de>, 2004-05-15
 * License: GNU GPL
 */

#include <stdio.h>
#include <string.h>
#include <netinet/in.h>

inline unsigned int nextpoweroftwo(const unsigned int arg)
{
	unsigned int pwr = 1;
	while (arg > pwr)
		pwr <<= 1;
	return pwr;
}

inline int sign(const int arg)
{
	return !arg? 0: (arg > 0? 1: -1);
}

/* search str in _sorted_ array argv; strings are at least 3 chars */
unsigned int search(const char* str, const int el, const char* arr[])
{
	if (!el)
		return 0;
	unsigned int ival = nextpoweroftwo(el+1) >> 1;
	unsigned int pos = ival - 1;
	const unsigned int tofind = htonl(*(unsigned int*)str);
	const char* sep = strchr(str, '\t');
	if (!sep) {
		sep = strchr(str, ' ');
		if (!sep)
			sep = strchr(str, '\n');
	}
	const size_t len = sep? sep-str: strlen(str);
	/* Zero out unused bits */
	const unsigned int compmask = len >= 4? 0xffffffff: ~((1 << (8*(4-len))) - 1);
	do {
		const unsigned int tocomp = htonl(*(unsigned int*)arr[pos]);
		ival >>= 1;
		//printf("%i\n", pos);
		int comp = (tofind - tocomp) & compmask;
		if (!comp) {
			const size_t len2 = strlen(arr[pos]);
			comp = memcmp(str, arr[pos], len<=len2? len: len2);
			if (!comp) {
				if (len == len2)
					return pos+1;
				else
					comp = len-len2;
			}
		}
		pos += sign(comp)*ival;
		if (pos > el-1 && ival) {
			const unsigned int newmin = pos-ival;
			ival = nextpoweroftwo(el-newmin) >> 1;
			pos = newmin + ival;
		}
	} while (ival);
	//printf("\n");
	return 0;
}

int main(int argc, const char* argv[])
{
	char buf[256];
	unsigned int inv = 0, ln = 0;
	if (argc > 1 && !strcmp(argv[1], "-v")) {
		argc--; argv++; inv=1;
	}
	if (!inv)
		while (!feof(stdin) && fgets(buf, 255, stdin)) {
			if (search(buf, argc-1, argv+1))
				printf("%s", buf);
			++ln;
		}
	else 
		while (!feof(stdin) && fgets(buf, 255, stdin)) {
			if (!search(buf, argc-1, argv+1))
				printf("%s", buf);
			++ln;
		}
	//printf("Matched %i lines against %i symbols\n", ln, argc-1);	
	return 0;
}

