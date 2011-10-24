#ifdef __x86_64__
/* 
 * Force the linker to use the older memcpy variant, so that the user programs
 * work on older systems
 */
__asm__(".symver memcpy,memcpy@GLIBC_2.2.5");
#endif
