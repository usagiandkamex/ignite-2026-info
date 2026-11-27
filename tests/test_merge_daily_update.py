from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import merge_daily_update as merge


class MergeDailyUpdateTests(TestCase):
    def setUp(self):
        self.repo = "owner/repo"
        self.sha = "a" * 40
        self.base = "b" * 40
        self.pr = {
            "state": "open", "draft": False, "title": "[日次情報更新] updates",
            "base": {"ref": "main", "sha": self.base, "repo": {"full_name": self.repo}},
            "head": {"sha": self.sha, "repo": {"full_name": self.repo}},
        }
        self.protection = {
            "enforce_admins": {"enabled": True},
            "required_status_checks": {
                "strict": True, "checks": [{"context": "build", "app_id": 15368}],
            },
        }

    def test_requires_enforced_and_authenticated_up_to_date_check(self):
        merge.require_protection(self.protection)
        for field in ("strict", "checks"):
            altered = deepcopy(self.protection)
            altered["required_status_checks"][field] = False if field == "strict" else []
            with self.assertRaises(ValueError):
                merge.require_protection(altered)
        altered = deepcopy(self.protection)
        altered["enforce_admins"]["enabled"] = False
        with self.assertRaises(ValueError):
            merge.require_protection(altered)
        altered = deepcopy(self.protection)
        altered["required_status_checks"]["checks"][0]["app_id"] = 1
        with self.assertRaises(ValueError):
            merge.require_protection(altered)

    def test_rejects_changed_head_base_or_foreign_pr(self):
        self.assertEqual(merge.require_pr(self.pr, self.repo, self.base), self.sha)
        for key, value in (("sha", "c" * 40), ("repo", {"full_name": "other/repo"})):
            changed = deepcopy(self.pr)
            changed["head"][key] = value
            with self.assertRaises(ValueError):
                merge.require_pr(changed, self.repo, self.base, self.sha)
        changed = deepcopy(self.pr)
        changed["base"]["sha"] = "c" * 40
        with self.assertRaises(ValueError):
            merge.require_pr(changed, self.repo, self.base)

    def test_rejects_files_and_renames_outside_data(self):
        merge.require_files([[{"filename": "data/sessions.json"}]])
        for item in (
            {"filename": ".github/workflows/pages.yml"},
            {"filename": "data/event.json", "previous_filename": "tools/build.py"},
        ):
            with self.assertRaises(ValueError):
                merge.require_files([[item]])
        with self.assertRaises(ValueError):
            merge.require_files([[]])

    @patch.object(merge.time, "sleep")
    @patch.object(merge, "api")
    def test_waits_for_matching_successful_pr_run(self, api, sleep):
        run = {"id": 1, "head_sha": self.sha, "pull_requests": [{"number": 7}],
               "status": "completed", "conclusion": "success"}
        api.side_effect = [{"workflow_runs": []}, {"workflow_runs": [run]}]
        merge.wait_for_build(self.repo, 7, self.sha)
        sleep.assert_called_once()

    @patch.object(merge, "api")
    def test_failed_or_superseded_build_does_not_merge(self, api):
        run = {"id": 1, "head_sha": self.sha, "pull_requests": [{"number": 7}],
               "status": "completed", "conclusion": "success"}
        api.return_value = {"workflow_runs": [run, {**run, "id": 2, "conclusion": "failure"}]}
        with self.assertRaisesRegex(ValueError, "failed"):
            merge.wait_for_build(self.repo, 7, self.sha)

    @patch.object(merge, "wait_for_build")
    @patch.object(merge, "api")
    @patch.object(merge, "gh")
    def test_merge_uses_only_validated_head(self, gh, api, wait):
        api.side_effect = [self.protection, self.pr, self.protection, self.pr]
        gh.side_effect = [json.dumps([[{"filename": "data/event.json"}]]), ""]
        with patch.dict(merge.os.environ, {
            "GITHUB_REPOSITORY": self.repo, "GITHUB_SHA": self.base, "PR_NUMBER": "7",
        }):
            merge.main()
        wait.assert_called_once_with(self.repo, 7, self.sha)
        self.assertEqual(gh.call_args_list[-1].args, (
            "pr", "merge", "7", "--repo", self.repo, "--squash", "--match-head-commit", self.sha,
        ))

    @patch.object(merge, "wait_for_build", side_effect=ValueError("build failed"))
    @patch.object(merge, "api")
    @patch.object(merge, "gh", return_value='[[{"filename":"data/event.json"}]]')
    def test_failed_build_never_requests_merge(self, gh, api, wait):
        api.side_effect = [self.protection, self.pr]
        with patch.dict(merge.os.environ, {
            "GITHUB_REPOSITORY": self.repo, "GITHUB_SHA": self.base, "PR_NUMBER": "7",
        }), self.assertRaisesRegex(ValueError, "build failed"):
            merge.main()
        self.assertEqual(gh.call_count, 1)
