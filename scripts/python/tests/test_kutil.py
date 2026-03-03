from kutil.config import read_config_sh, get_kernel_project_package, list_files, list_specs, get_kernel_projects, get_package_archs
import unittest

class MiscTests(unittest.TestCase):
    def test_config_sh(self):
        config = read_config_sh('tests/kutil/rpm/krnf')
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
        self.assertEqual(get_kernel_project_package('tests/kutil/rpm/klp'),
                         ('SUSE:SLE-15-SP7:Update:Products:SLERT', 'kernel-livepatch-SLE15-SP7-RT_Update_0'))

    def test_lsspec(self):
        self.assertEqual(list_specs('tests/kutil/rpm/krna'), ['kernel-azure', 'kernel-source-azure', 'kernel-syms-azure'])
        self.assertEqual(list_specs('tests/kutil/rpm/kgr'), ['kernel-livepatch-SLE15_Update_7'])

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

    def test_pkg_repos(self):
        self.assertEqual(get_kernel_projects('tests/kutil/rpm/krn'), {
             'IBS': {'': 'SUSE:SLE-15-SP6:Update', 'ARM': 'openSUSE.org:openSUSE:Step:15-SP6'},
             'OBS': {'': 'SUSE:SLE-15-SP6:GA', 'ARM': 'openSUSE:Step:15-SP6'},
            })
        self.assertEqual(get_kernel_projects('tests/kutil/rpm/krna'), {
             'IBS': {'': 'SUSE:SLE-15-SP6:GA', 'ARM': 'openSUSE.org:openSUSE:Step:15-SP6'},
             'OBS': {'': 'SUSE:SLE-15-SP6:GA', 'ARM': 'openSUSE:Step:15-SP6'},
            })
        self.assertEqual(get_kernel_projects('tests/kutil/rpm/krnf'), {
            'IBS': {'': 'openSUSE.org:openSUSE:Factory',
                    'ARM': 'openSUSE.org:openSUSE:Factory:ARM',
                    'LEGACYX86': 'openSUSE.org:openSUSE:Factory:LegacyX86',
                    'PPC': 'openSUSE.org:openSUSE:Factory:PowerPC',
                    'RISCV': 'openSUSE.org:openSUSE:Factory:RISCV',
                    'S390': 'openSUSE.org:openSUSE:Factory:zSystems'},
            'OBS': {'': 'openSUSE:Factory',
                    'ARM': 'openSUSE:Factory:ARM',
                    'LEGACYX86': 'openSUSE:Factory:LegacyX86',
                    'PPC': 'openSUSE:Factory:PowerPC',
                    'RISCV': 'openSUSE:Factory:RISCV',
                    'S390': 'openSUSE:Factory:zSystems'},

            })
        self.assertEqual(get_kernel_projects('tests/kutil/rpm/kgr'), {
            'IBS': {'': 'SUSE:Maintenance:9216'},
            'OBS': {},
            })
        self.assertEqual(get_kernel_projects('tests/kutil/rpm/klp'), {
            'IBS': {'': 'SUSE:SLE-15-SP7:Update:Products:SLERT'},
            'OBS': {},
            })

    def test_package_archs(self):
        self.assertEqual(get_package_archs('tests/kutil/rpm/krn'),
                          ['aarch64', 'armv7hl', 'armv7l', 'ppc64le', 's390x', 'x86_64'])
        self.assertEqual(get_package_archs('tests/kutil/rpm/krna'),
                          ['aarch64', 'x86_64'])
        self.assertEqual(get_package_archs('tests/kutil/rpm/krnf'),
                          ['aarch64', 'armv6hl', 'armv6l', 'armv7hl', 'armv7l', 'i386', 'i486', 'i586', 'i686', 'ppc64le', 'riscv64', 's390x', 'x86_64'])
        self.assertEqual(get_package_archs('tests/kutil/rpm/krnf', ['kernel-zfcpdump']),
                          ['s390x'])
        self.assertEqual(get_package_archs('tests/kutil/rpm/kgr'),
                          ['ppc64le', 'x86_64'])
        self.assertEqual(get_package_archs('tests/kutil/rpm/klp'),
                          ['x86_64'])
