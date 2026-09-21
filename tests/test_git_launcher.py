"""Regression coverage for starting Git MCP without an activated environment."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.mcp.git import _resolve_uvx


class GitLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.executable = "uvx.exe" if os.name == "nt" else "uvx"
        self.interpreter_bin = root / "python"
        self.project = root / "project"
        scripts = "Scripts" if os.name == "nt" else "bin"
        self.project_bin = self.project / ".venv" / scripts
        self.interpreter_bin.mkdir()
        self.project_bin.mkdir(parents=True)
        for patcher in (
            patch("src.mcp.git.PROJECT_ROOT", self.project),
            patch("src.mcp.git.sys.executable", str(self.interpreter_bin / "python.exe")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_project_environment_is_used_when_uvx_is_not_on_path(self):
        installed = self.project_bin / self.executable
        installed.touch()
        with patch("src.mcp.git.shutil.which", return_value=None):
            self.assertEqual(_resolve_uvx(), str(installed.resolve()))

    def test_running_interpreter_environment_takes_precedence(self):
        installed = self.interpreter_bin / self.executable
        installed.touch()
        (self.project_bin / self.executable).touch()
        with patch("src.mcp.git.shutil.which", return_value="another-uvx"):
            self.assertEqual(_resolve_uvx(), str(installed.resolve()))

    def test_system_installation_is_used_without_a_local_copy(self):
        with patch("src.mcp.git.shutil.which", return_value="system-uvx"):
            self.assertEqual(_resolve_uvx(), "system-uvx")

    def test_missing_dependency_explains_how_to_install_it(self):
        with patch("src.mcp.git.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "python -m pip install uv"):
                _resolve_uvx()


if __name__ == "__main__":
    unittest.main()
