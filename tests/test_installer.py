"""Isolated unit & integration tests for the Phase 7 Universal Installer."""

from pathlib import Path
import tempfile
import unittest

from agent_token_receipt.installer import UniversalInstaller
from agent_token_receipt.installer.templates import MANAGED_MARKER_MD, MANAGED_MARKER_TOML


class TestUniversalInstaller(unittest.TestCase):
    """Test environment detection, permission prompts, backups, idempotency, conflicts, and uninstall."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.ws = self.root / "workspace"
        self.home.mkdir(parents=True, exist_ok=True)
        self.ws.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _populate_all_six_global_agents(self):
        (self.home / ".claude").mkdir(parents=True, exist_ok=True)
        (self.home / ".codex").mkdir(parents=True, exist_ok=True)
        (self.home / ".cursor").mkdir(parents=True, exist_ok=True)
        (self.home / ".codeium" / "windsurf").mkdir(parents=True, exist_ok=True)
        (self.home / ".gemini" / "antigravity").mkdir(parents=True, exist_ok=True)
        (self.home / ".gemini" / "tmp").mkdir(parents=True, exist_ok=True)

    def test_antigravity_does_not_falsely_trigger_gemini_cli(self):
        """Presence of ~/.gemini/antigravity alone must detect Antigravity, not Gemini CLI."""
        (self.home / ".gemini" / "antigravity").mkdir(parents=True, exist_ok=True)
        installer = UniversalInstaller(home_dir=self.home, probe_path_binaries=False)
        statuses = {st.integration.agent_key: st for st in installer.detector.detect_all(workspace=self.ws)}
        self.assertTrue(statuses["antigravity"].global_detection.detected)
        self.assertFalse(statuses["gemini_cli"].global_detection.detected)

    def test_empty_home_detects_no_agents(self):
        installer = UniversalInstaller(home_dir=self.home, probe_path_binaries=False)
        plan = installer.plan_install(scope="auto", workspace=self.ws)
        self.assertEqual(plan.artifacts, [])
        self.assertEqual(plan.detected_agents, [])

    def test_dry_run_and_permission_refusal_make_zero_changes(self):
        (self.home / ".claude").mkdir(parents=True, exist_ok=True)
        installer = UniversalInstaller(home_dir=self.home, probe_path_binaries=False)
        plan = installer.plan_install(scope="global", workspace=self.ws)
        self.assertEqual(len(plan.artifacts), 1)

        dry_res = installer.execute_install(plan, dry_run=True)
        self.assertEqual(dry_res.actions[0].status, "would_install")
        self.assertFalse(plan.artifacts[0].target_path.exists())

        aborted_res = installer.execute_install(plan, yes=False, confirm_callback=lambda _: False)
        self.assertTrue(aborted_res.aborted)
        self.assertFalse(plan.artifacts[0].target_path.exists())

    def test_install_all_six_agents_global_idempotent_and_uninstall(self):
        self._populate_all_six_global_agents()
        installer = UniversalInstaller(home_dir=self.home, probe_path_binaries=False)
        plan = installer.plan_install(scope="global", workspace=self.ws)

        # 6 agents -> 9 global artifacts (claude:1, codex:1, cursor:2, windsurf:2, antigravity:1, gemini_cli:2)
        self.assertEqual(len(plan.artifacts), 9)
        self.assertTrue(any("Codex" in w and "$agent-billing" in w for w in plan.warnings))
        self.assertTrue(any("Cursor" in w for w in plan.warnings))
        self.assertTrue(any("Windsurf" in w for w in plan.warnings))

        first = installer.execute_install(plan, yes=True)
        self.assertTrue(all(a.status == "installed" for a in first.actions))

        # Check exact files & markers
        expected_files = [
            self.home / ".claude" / "skills" / "agent-billing" / "SKILL.md",
            self.home / ".codex" / "skills" / "agent-billing" / "SKILL.md",
            self.home / ".cursor" / "commands" / "agent-billing.md",
            self.home / ".cursor" / "skills" / "agent-billing" / "SKILL.md",
            self.home / ".codeium" / "windsurf" / "global_workflows" / "agent-billing.md",
            self.home / ".codeium" / "windsurf" / "skills" / "agent-billing" / "SKILL.md",
            self.home / ".gemini" / "config" / "skills" / "agent-billing" / "SKILL.md",
            self.home / ".gemini" / "commands" / "agent-billing.toml",
            self.home / ".gemini" / "skills" / "agent-billing" / "SKILL.md",
        ]
        for p in expected_files:
            self.assertTrue(p.is_file(), f"Expected installed artifact missing: {p}")
            text = p.read_text(encoding="utf-8")
            self.assertIn("agent-token-receipt generate", text)
            if p.suffix == ".toml":
                self.assertIn(MANAGED_MARKER_TOML, text)
            else:
                self.assertIn(MANAGED_MARKER_MD, text)
                self.assertNotIn("\\", text)

        # Second install must be strictly idempotent
        second = installer.execute_install(plan, yes=True)
        self.assertTrue(all(a.status == "unchanged" for a in second.actions))

        # Doctor verification
        doc = installer.doctor(workspace=self.ws)
        self.assertTrue(doc.catalogue_loaded)
        self.assertGreaterEqual(doc.catalogue_model_count, 10)
        for ag in doc.agents:
            self.assertTrue(ag.detected_global)
            self.assertEqual(ag.missing_artifacts, [])
            self.assertTrue(len(ag.installed_artifacts) >= 1)

        # Uninstall cleans every artifact safely without leaving orphan skill dirs
        un = installer.uninstall(scope="global", workspace=self.ws, yes=True)
        self.assertTrue(all(a.status == "removed" for a in un.actions))
        for p in expected_files:
            self.assertFalse(p.exists())
        # Parent config folders themselves (.claude, .cursor, etc.) remain untouched
        self.assertTrue((self.home / ".claude").is_dir())
        self.assertTrue((self.home / ".cursor").is_dir())

    def test_conflict_preservation_backup_and_restore(self):
        """User-authored files without managed marker are preserved by default and backed up/restored with --force."""
        (self.home / ".cursor" / "commands").mkdir(parents=True, exist_ok=True)
        custom_cmd = self.home / ".cursor" / "commands" / "agent-billing.md"
        original_content = "# User custom command - DO NOT OVERWRITE\n"
        custom_cmd.write_text(original_content, encoding="utf-8")

        installer = UniversalInstaller(home_dir=self.home, probe_path_binaries=False)
        plan = installer.plan_install(scope="global", workspace=self.ws, agents=["cursor"])

        # Without force: preserves user's custom file
        safe_res = installer.execute_install(plan, yes=True, force=False)
        statuses = {a.target_path: a.status for a in safe_res.actions}
        self.assertEqual(statuses[custom_cmd], "skipped_conflict")
        self.assertEqual(custom_cmd.read_text(encoding="utf-8"), original_content)

        # With force: backs up original and installs new command
        forced_res = installer.execute_install(plan, yes=True, force=True)
        forced_action = [a for a in forced_res.actions if a.target_path == custom_cmd][0]
        self.assertEqual(forced_action.status, "updated")
        self.assertIsNotNone(forced_action.backup_path)
        self.assertTrue(forced_action.backup_path.is_file())
        self.assertIn(MANAGED_MARKER_MD, custom_cmd.read_text(encoding="utf-8"))

        # Uninstall restores original user content and deletes backup
        un = installer.uninstall(scope="global", workspace=self.ws, agents=["cursor"], yes=True)
        restored = [a for a in un.actions if a.target_path == custom_cmd][0]
        self.assertEqual(restored.status, "restored_backup")
        self.assertEqual(custom_cmd.read_text(encoding="utf-8"), original_content)
        self.assertFalse(forced_action.backup_path.exists())

    def test_shared_project_skill_reference_counting(self):
        """Shared .agents/skills/agent-billing/SKILL.md stays present until all owning agents uninstall."""
        installer = UniversalInstaller(home_dir=self.home, probe_path_binaries=False)
        plan = installer.plan_install(
            scope="project",
            workspace=self.ws,
            agents=["antigravity", "codex"],
        )
        res = installer.execute_install(plan, yes=True)
        shared_skill = self.ws / ".agents" / "skills" / "agent-billing" / "SKILL.md"
        self.assertTrue(shared_skill.is_file())
        self.assertEqual([a.status for a in res.actions], ["installed", "unchanged"])

        un1 = installer.uninstall(scope="project", workspace=self.ws, agents=["codex"], yes=True)
        self.assertEqual(un1.actions[0].status, "kept_shared")
        self.assertTrue(shared_skill.is_file())

        un2 = installer.uninstall(scope="project", workspace=self.ws, agents=["antigravity"], yes=True)
        self.assertEqual(un2.actions[0].status, "removed")
        self.assertFalse(shared_skill.exists())

    def test_rendered_templates_include_posix_python_fallback_and_venv_doctor_note(self):
        """Templates embed a backslash-free Python fallback and doctor warns when CLI lives only in a venv."""
        from unittest.mock import patch
        from agent_token_receipt.installer.templates import (
            render_billing_skill_md,
            render_command_markdown,
            render_gemini_cli_toml,
        )

        win_venv_py = r"C:\demo\.venv\Scripts\python.exe"
        skill_md = render_billing_skill_md(python_executable=win_venv_py)
        cmd_md = render_command_markdown("Cursor", "Slash Command", python_executable=win_venv_py)
        toml_txt = render_gemini_cli_toml(python_executable=win_venv_py)

        for rendered in (skill_md, cmd_md, toml_txt):
            self.assertIn("C:/demo/.venv/Scripts/python.exe", rendered)
            self.assertNotIn("\\", rendered)

        venv_dir = self.root / "venv"
        fake_cli = venv_dir / "Scripts" / "agent-token-receipt.exe"
        fake_cli.parent.mkdir(parents=True, exist_ok=True)
        fake_cli.write_text("", encoding="utf-8")

        installer = UniversalInstaller(home_dir=self.home, probe_path_binaries=False)
        with patch("agent_token_receipt.installer.installer.shutil.which", return_value=str(fake_cli)), patch(
            "agent_token_receipt.installer.installer.sys.prefix", str(venv_dir)
        ), patch(
            "agent_token_receipt.installer.installer.sys.base_prefix", str(self.root / "sys_py")
        ):
            report = installer.doctor(workspace=self.ws)
        self.assertTrue(any("virtual environment" in issue for issue in report.issues))


if __name__ == "__main__":
    unittest.main()

