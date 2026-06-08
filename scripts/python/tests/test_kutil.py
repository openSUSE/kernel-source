from kutil.config import read_config_sh, get_kernel_project_package, list_files, list_specs, get_kernel_projects, get_package_archs, SrcVersion, compute_patchversion
from kutil import pathlib_compat
from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil

class MiscTests(unittest.TestCase):
    def test_config_sh(self):
        config = read_config_sh('tests/kutil/rpm/krnf')
        self.assertEqual(config['variant'], '')
        self.assertEqual(config['multibuild'], 'Yes')
        self.assertEqual(config.getboolean('multibuild'), True)
        self.assertEqual(config.getboolean('build_pdf'), False)
        self.assertEqual(config.getboolean('foobar'), False)
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

    def test_srcversion(self):
        self.assertRaises(Exception, SrcVersion('1.2.4el4'))
        testdata = [
        ('1.2.3-rc4', None, {
            'version': '1',
            'patchlevel': '2',
            'sublevel': '3',
            'extraversion': '-rc4',
            }),
        ('1.2-foobar', '1.2.0-foobar', {
            'version': '1',
            'patchlevel': '2',
            'sublevel': '0',
            'extraversion': '-foobar',
            }),
        ('7.0', '7.0.0', {
            'version': '7',
            'patchlevel': '0',
            'sublevel': '0',
            'extraversion': '',
            }),
        ]
        for inp, outs, outd in testdata:
            if not outs:
                outs = inp
            sv = SrcVersion(inp)
            self.assertEqual(str(sv), outs)
            self.assertEqual(dict(sv), outd)

class TestComputePatchversion(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        self.rpmdir = self.base / 'rpm'
        self.rpmdir.mkdir()
        self.patches_orig = Path(__file__).parent / 'kutil' / 'patchversion'
        self.patches = self.base / 'patches.suse'
        self.patches.symlink_to(self.patches_orig)
        self.packagedir = self.base / 'package'
        self.packagedir.mkdir()
        self.config_sh = self.rpmdir / 'config.sh'
        self.config_sh_pkg = self.packagedir / 'config.sh'
        self.series_conf = self.base / 'series.conf'
        self.series_conf_pkg = self.packagedir / 'series.conf'
        self.compute_orig = Path(__file__).parents[2] / 'compute-PATCHVERSION'
        self.guards_orig = Path(__file__).parents[2] / 'guards'
        self.compute_rpm = self.rpmdir / 'compute-PATCHVERSION'
        self.guards_rpm = self.rpmdir / 'guards'
        self.compute_pkg = self.packagedir / 'compute-PATCHVERSION'
        self.guards_pkg = self.packagedir / 'guards'

    def tearDown(self):
        self.tmpdir.cleanup()
        self.tmpdir = None

    def run_pipeline(self, cmd, cwd, expect_error=False):
        pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        out, err = pipe.communicate()
        if err and not expect_error:
            print(cmd, err)
        return pipe, out, err

    def run_test(self, test_fn, expect_error=False):
        self.compute_rpm.symlink_to(self.compute_orig)
        self.guards_rpm.symlink_to(self.guards_orig)
        test_fn(*self.run_pipeline([self.compute_rpm], self.base, expect_error))
        shutil.copy(self.compute_orig, self.compute_pkg)
        shutil.copy(self.guards_orig, self.guards_pkg)
        try:
            shutil.copy(self.config_sh, self.config_sh_pkg)
        except FileNotFoundError:
            None
        try:
            shutil.copy(self.series_conf, self.series_conf_pkg)
        except FileNotFoundError:
            None
        test_fn(*self.run_pipeline([self.compute_pkg, '--patches', self.base], self.packagedir, expect_error))

    def test_compute_fn_no_config(self):
        self.series_conf.write_text('''
patches.suse/sublevel_4 # change sublevel
''')
        with self.assertRaisesRegex(FileNotFoundError, 'config[.]sh'):
            ver = compute_patchversion(self.rpmdir, self.base, self.base)

    def test_compute_fn_no_series(self):
        self.config_sh.write_text('SRCVERSION=1.2')
        with self.assertRaisesRegex(RuntimeError, 'series[.]conf'):
            ver = compute_patchversion(self.rpmdir, self.base, self.base)

    def test_compute_fn_missing_patch(self):
        self.config_sh.write_text('SRCVERSION=1.2')
        self.series_conf.write_text('''
patches.suse/no_such.patch
''')
        with self.assertRaisesRegex(RuntimeError, 'no_such[.]patch'):
            ver = compute_patchversion(self.rpmdir, self.base, self.base)

    def test_compute_fn(self):
        self.config_sh.write_text('SRCVERSION=1.2')
        self.series_conf.write_text('''
patches.suse/sublevel_4 # change sublevel
''')
        ver = compute_patchversion(self.rpmdir, self.base, self.base)
        self.assertEqual('1.2.4', str(ver))

    def test_empty(self):
        def test_fn(pipe, out, err):
            # script retruns 0 and prints .0.0, not a desirable outcome, not tested
            self.assertTrue(b'config.sh' in err)
        self.run_test(test_fn, True)

    def test_no_series(self):
        self.config_sh.write_text('SRCVERSION=1.2')

        def test_fn(pipe, out, err):
            # script retruns 0 and prints .0.0, not a desirable outcome, not tested
            self.assertTrue(b'series.conf' in err)
        self.run_test(test_fn, True)

    def test_nonexistent_patch(self):
        self.config_sh.write_text('SRCVERSION=1.2-rc3')
        self.series_conf.write_text('''
patches.suse/no_such.patch
''')

        def test_fn(pipe, out, err):
            self.assertNotEqual(0, pipe.returncode)
            self.assertEqual(b'', out.strip())
            self.assertTrue(b'no_such.patch' in err)
        self.run_test(test_fn, True)

    def test_empty_series(self):
        self.config_sh.write_text('SRCVERSION=1.2')
        self.series_conf.write_text('')

        def test_fn(pipe, out, err):
            self.assertEqual(0, pipe.returncode)
            self.assertEqual(b'1.2.0', out.strip())
            self.assertEqual(b'', err)
        self.run_test(test_fn)

    def test_noextra(self):
        self.config_sh.write_text('SRCVERSION=1.2-rc3')
        self.series_conf.write_text('''
patches.suse/no_extraversion.diff
''')

        def test_fn(pipe, out, err):
            self.assertEqual(0, pipe.returncode)
            self.assertEqual(b'1.2.0', out.strip())
            self.assertEqual(b'', err)
        self.run_test(test_fn)

    def test_commented(self):
        self.config_sh.write_text('SRCVERSION=1.2')
        self.series_conf.write_text('''
# patches.suse/sublevel_4
''')

        def test_fn(pipe, out, err):
            self.assertEqual(0, pipe.returncode)
            self.assertEqual(b'1.2.0', out.strip())
            self.assertEqual(b'', err)
        self.run_test(test_fn)

    def test_guarded(self):
        self.config_sh.write_text('SRCVERSION=1.2')
        self.series_conf.write_text('''
+unused patches.suse/sublevel_4
''')

        def test_fn(pipe, out, err):
            self.assertEqual(0, pipe.returncode)
            self.assertEqual(b'1.2.0', out.strip())
            self.assertEqual(b'', err)
        self.run_test(test_fn)

    def test_sublevel(self):
        self.config_sh.write_text('SRCVERSION=1.2')
        self.series_conf.write_text('''
patches.suse/sublevel_4 # change sublevel
''')

        def test_fn(pipe, out, err):
            self.assertEqual(0, pipe.returncode)
            self.assertEqual(b'1.2.4', out.strip())
            self.assertEqual(b'', err)
        self.run_test(test_fn)

    def test_not_patches(self):
        self.config_sh.write_text('SRCVERSION=1.2')
        self.series_conf.write_text('''
patches.suse/sublevel_4_before
patches.suse/sublevel_4_after
''')

        def test_fn(pipe, out, err):
            self.assertEqual(0, pipe.returncode)
            self.assertEqual(b'1.2.0', out.strip())
            self.assertEqual(b'', err)
        self.run_test(test_fn)
