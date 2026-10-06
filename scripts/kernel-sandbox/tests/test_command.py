import unittest
from pathlib import Path

from libs.command import get_printable_cmd


class TestGetPrintableCmd(unittest.TestCase):
    def test_get_printable_cmd_scenarios(self):
        test_cases = [
            ("multi_arg", ["qemu", "-cpu", "max"], ["qemu \\", "-cpu", "max"]),
            ("single_element", ["ls"], ["ls"]),
            ("empty_list", [], ""),
            ("none_input", None, ""),
            ("shell_quoting", ["echo", "hello world", "a&&b", "$HOME"], ["'hello world'", "'a&&b'", "'$HOME'"]),
            ("non_string_types", ["qemu", "-m", 4096, Path("/tmp/img")], ["qemu \\", "-m", "4096", "/tmp/img"]),
        ]

        for name, cmd, expected in test_cases:
            with self.subTest(case=name):
                result = get_printable_cmd(cmd)
                if isinstance(expected, list):
                    for item in expected:
                        self.assertIn(item, result)
                else:
                    self.assertEqual(result, expected)

    def test_get_printable_cmd_indentation(self):
        cmd = ["qemu", "-m", "4096"]
        result = get_printable_cmd(cmd, indent_spaces=4)
        self.assertIn("\n    qemu \\\n        -m \\\n        4096", result)
