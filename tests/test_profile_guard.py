"""默认 profile 必须在仓库外：路径防呆 + 登录拒绝（零网络）。"""

from __future__ import annotations

import pathlib
import unittest
from unittest import mock

from tools.selection.access import douyin
from tools.selection.access import tieba


REPO = pathlib.Path(__file__).resolve().parents[1]
IN_REPO = REPO / "docs" / "validation" / "v10" / "douyin-access" / "profile"


class DefaultProfileTests(unittest.TestCase):
    def test_douyin_default_profile_is_outside_repo(self):
        self.assertFalse(douyin.profile_in_repo(douyin.DEFAULT_PROFILE))
        self.assertNotIn(str(REPO).lower(), str(douyin.DEFAULT_PROFILE).lower())

    def test_tieba_default_profile_is_outside_repo(self):
        self.assertFalse(tieba.profile_in_repo(tieba.DEFAULT_PROFILE))
        self.assertNotIn(str(REPO).lower(), str(tieba.DEFAULT_PROFILE).lower())

    def test_defaults_are_under_dsh_tools(self):
        for profile in (douyin.DEFAULT_PROFILE, tieba.DEFAULT_PROFILE):
            self.assertIn(".dsh", str(profile))
            self.assertIn("tools", str(profile))


class DoctorGuardTests(unittest.TestCase):
    def test_douyin_doctor_flags_in_repo_profile(self):
        out = douyin.doctor(IN_REPO)
        self.assertTrue(out["profile_in_repo"])
        self.assertIn("profile_inside_repo", out["warning"])
        self.assertEqual(out["network"], "none")

    def test_tieba_doctor_flags_in_repo_profile(self):
        out = tieba.doctor(IN_REPO)
        self.assertTrue(out["profile_in_repo"])
        self.assertIn("profile_inside_repo", out["warning"])
        self.assertEqual(out["network"], "none")

    def test_default_profile_has_no_warning(self):
        self.assertIsNone(douyin.doctor(douyin.DEFAULT_PROFILE).get("warning"))
        self.assertIsNone(tieba.doctor(tieba.DEFAULT_PROFILE).get("warning"))


class LoginGuardTests(unittest.TestCase):
    def test_douyin_login_rejects_in_repo_profile_without_browser(self):
        spy = mock.Mock()
        with mock.patch.object(douyin, "browser_mod", spy), \
                mock.patch.object(douyin, "session_mod", spy, create=True):
            out = douyin.login(IN_REPO, budget=mock.Mock())
        self.assertEqual(out["status"], "rejected")
        self.assertEqual(out["stop"], "profile_inside_repo")
        self.assertFalse(out["signed_in"])
        self.assertEqual(spy.mock_calls, [])          # 没碰浏览器

    def test_tieba_login_rejects_in_repo_profile_without_browser(self):
        out = tieba.login(IN_REPO)
        self.assertEqual(out["status"], "rejected")
        self.assertEqual(out["stop"], "profile_inside_repo")
        self.assertEqual(out["network"], "none")

    def test_tieba_login_outside_repo_keeps_offline_branch(self):
        out = tieba.login(tieba.DEFAULT_PROFILE)
        self.assertEqual(out["stop"], "unsupported_offline")


class GitignoreTests(unittest.TestCase):
    """仓库里绝不能出现 profile / Cookies：gitignore 必须兜住。"""

    def setUp(self):
        self.text = (REPO / ".gitignore").read_text(encoding="utf-8")

    def test_profile_and_cookies_are_ignored(self):
        self.assertIn("**/profile/", self.text)
        self.assertIn("**/Cookies", self.text)

    def test_no_cookie_db_inside_docs(self):
        """登录态文件不得留在仓库：docs/ 下不应有任何 Cookies 数据库。"""
        hits = [p for p in REPO.glob("docs/**/Cookies*") if p.is_file()]
        self.assertEqual(hits, [], f"仓库内不应存在 cookie 数据库: {hits}")

    def test_default_profile_dirs_are_gone(self):
        for rel in ("docs/validation/v10/douyin-access/profile",
                    "docs/validation/v10/tieba/profile"):
            self.assertFalse((REPO / rel).exists(), f"{rel} 不应存在")


if __name__ == "__main__":
    unittest.main()
