/*
 * main.c - A demo kernel module.
 *
 * Andreas Gruenbacher <agruen@suse.de>, SUSE Labs, 2003-2004.
 */

#include <linux/module.h>
#include <linux/init.h>

MODULE_AUTHOR("Andreas Gruenbacher <agruen@suse.de>");
MODULE_DESCRIPTION("A demo module");
MODULE_LICENSE("GPL");

int param;

MODULE_PARM(param, "i");
MODULE_PARM_DESC(param, "Example parameter");

void exported_function(void)
{
	printk(KERN_INFO "Exported function called.\n");
}
EXPORT_SYMBOL(exported_function);

int __init init_hello(void)
{
	printk(KERN_INFO "Hello world.\n");
	return 0;
}

void __exit exit_hello(void)
{
	printk(KERN_INFO "Goodbye world.\n");
}

module_init(init_hello);
module_exit(exit_hello);
