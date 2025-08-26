from kutil.config import read_config_sh, get_kernel_project_package, list_files
import unittest

class MiscTests(unittest.TestCase):
    def test_config_sh(self):
        config = read_config_sh('tests/kutil/rpm/krnf/config.sh')
        self.assertEqual(config['variant'], '')
        self.assertEqual(config['multibuild'], 'Yes')
        self.assertEqual(config.getboolean('multibuild'), True)
        self.assertEqual(config['bugzilla_product'], 'openSUSE Tumbleweed')

    def test_pkg_name(self):
        self.assertEqual(get_kernel_project_package('tests/kutil/rpm/krn'), ('SUSE:SLE-15-SP6:Update', 'kernel-source'))
        self.assertEqual(get_kernel_project_package('tests/kutil/rpm/krna'), ('SUSE:SLE-15-SP6:GA', 'kernel-source-azure'))
        self.assertEqual(get_kernel_project_package('tests/kutil/rpm/krnf'), ('openSUSE:Factory', 'kernel-source'))
        self.assertEqual(get_kernel_project_package('tests/kutil/rpm/kgr'),
                         ('SUSE:Maintenance:9216', 'kernel-livepatch-SLE15_Update_7'))

    def test_list_files(self):
        result = [ f for f in sorted( '''
a directory/a file in a directory
a directory/another file in a directory
a directory/.a hidden file in a directory
another directory/a file in another directory
a file
another file
.a hidden file
'''.splitlines()) if len(f) > 0 ]
        self.assertEqual(list_files('tests/kutil/dir'), result)
