import io
import logging
import unittest
from contextlib import redirect_stderr, redirect_stdout

from libs.console import (
    LOGGER_NAME,
    configure_logging,
    get_logger,
    print_phase_header,
)


class TestPrintPhaseHeader(unittest.TestCase):
    def test_print_phase_header_scenarios(self):
        test_cases = [
            (
                "with_details",
                {"phase_title": "Boot Test", "details": ["Arch: arm64", "Timeout: 30s"], "width": 70, "character": "="},
                ["=", "  Boot Test", "    - Arch: arm64", "    - Timeout: 30s"]
            ),
            (
                "without_details",
                {"phase_title": "Build Phase"},
                ["  Build Phase"]
            ),
            (
                "custom_width_and_character",
                {"phase_title": "Custom", "width": 10, "character": "*"},
                ["**********"]
            ),
            (
                "empty_title",
                {"phase_title": ""},
                ["=" * 70]
            ),
            (
                "custom_indentation",
                {"phase_title": "Indented", "details": ["Detail"], "indent_spaces": 4},
                ["    Indented", "      - Detail"]
            ),
        ]

        for name, kwargs, expected_items in test_cases:
            with self.subTest(case=name):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    print_phase_header(**kwargs)
                output = buf.getvalue()

                for item in expected_items:
                    self.assertIn(item, output)

                if name == "without_details":
                    self.assertNotIn("- ", output)
                elif name == "custom_width_and_character":
                    self.assertNotIn("=" * 10, output)


class TestConfigureLogging(unittest.TestCase):
    def tearDown(self):
        logger = logging.getLogger(LOGGER_NAME)
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True

    def test_configure_logging_scenarios(self):
        test_cases = [
            (
                "info_and_debug_stdout",
                (logging.DEBUG, [("info", "workspace ready"), ("debug", "host compiler: gcc")]),
                {"out": "[INFO] workspace ready\n[DEBUG] host compiler: gcc\n", "err": ""}
            ),
            (
                "warning_and_error_stderr",
                (logging.INFO, [("warning", "cache directory missing"), ("error", "SSH never came up")]),
                {"out": "", "err": "[WARNING] cache directory missing\n[ERROR] SSH never came up\n"}
            ),
            (
                "default_level_suppresses_debug",
                (logging.INFO, [("debug", "should not appear"), ("info", "should appear")]),
                {"out_not_in": "should not appear", "out_in": "should appear"}
            ),
            (
                "empty_message",
                (logging.INFO, [("info", "")]),
                {"out": "[INFO] \n"}
            ),
        ]

        for name, (level, messages), expectations in test_cases:
            with self.subTest(case=name):
                out, err = io.StringIO(), io.StringIO()
                test_logger_name = f"test_logger_{name}"

                with redirect_stdout(out), redirect_stderr(err):
                    configure_logging(logger_name=test_logger_name, level=level)
                    logger = get_logger(name="child", base_name=test_logger_name)

                    for level_name, msg in messages:
                        getattr(logger, level_name)(msg)

                if "out" in expectations:
                    self.assertEqual(out.getvalue(), expectations["out"])
                if "err" in expectations:
                    self.assertEqual(err.getvalue(), expectations["err"])
                if "out_not_in" in expectations:
                    self.assertNotIn(expectations["out_not_in"], out.getvalue())
                if "out_in" in expectations:
                    self.assertIn(expectations["out_in"], out.getvalue())

    def test_reconfigure_no_duplicate_handlers(self):
        """calling configure_logging multiple times doesn't spam duplicated lines."""
        out = io.StringIO()
        test_logger_name = "duplicate_test_logger"

        with redirect_stdout(out):
            configure_logging(logger_name=test_logger_name)
            configure_logging(logger_name=test_logger_name)

            logger = get_logger(base_name=test_logger_name)
            logger.info("single line")

        # If handlers duplicated, we would see this line twice
        self.assertEqual(out.getvalue(), "[INFO] single line\n")

    def test_get_logger_auto_provisioning(self):
        """get_logger automatically provisions a logger."""
        out = io.StringIO()
        test_logger_name = "auto_provision_test"

        self.assertFalse(logging.getLogger(test_logger_name).hasHandlers())

        with redirect_stdout(out):
            logger = get_logger(base_name=test_logger_name)
            logger.info("auto configured")

        self.assertTrue(logging.getLogger(test_logger_name).hasHandlers())
        self.assertEqual(out.getvalue(), "[INFO] auto configured\n")
