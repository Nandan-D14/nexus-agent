# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.sandbox_components.files import raise_sandbox_io_error


class RaiseSandboxIoErrorTests(TestCase):
    def test_missing_file_traceback_becomes_file_not_found(self) -> None:
        stderr = (
            "Traceback (most recent call last):\n"
            '  File "/usr/lib/python3.10/pathlib.py", line 1134, in read_text\n'
            "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/missing.md'\n"
        )
        with self.assertRaises(FileNotFoundError) as caught:
            raise_sandbox_io_error("/tmp/missing.md", stderr, action="read file")
        self.assertEqual(str(caught.exception), "File not found: /tmp/missing.md")
        self.assertNotIn("Traceback", str(caught.exception))
        self.assertNotIn("pathlib.py", str(caught.exception))

    def test_missing_directory_becomes_directory_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError) as caught:
            raise_sandbox_io_error(
                "/tmp/gone",
                "ls: cannot access '/tmp/gone': No such file or directory",
                action="list directory",
            )
        self.assertEqual(str(caught.exception), "Directory not found: /tmp/gone")

    def test_other_failures_use_one_line_runtime_error(self) -> None:
        stderr = (
            "Traceback (most recent call last):\n"
            "PermissionError: [Errno 13] Permission denied\n"
        )
        with self.assertRaises(RuntimeError) as caught:
            raise_sandbox_io_error("/tmp/secret.md", stderr, action="read file")
        self.assertEqual(str(caught.exception), "Failed to read file /tmp/secret.md")
        self.assertNotIn("Traceback", str(caught.exception))
        self.assertNotIn("PermissionError", str(caught.exception))
