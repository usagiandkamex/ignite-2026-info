"""Merge a newly created daily update after its protected PR check succeeds."""

import json
import os
import re
import subprocess
import time


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)


def api(path):
    return json.loads(gh("api", path))


def require_protection(repo):
    prefix = f"repos/{repo}"
    for rule in api(f"{prefix}/rules/branches/main?per_page=100"):
        if not (
            rule["type"] == "required_status_checks"
            and rule["ruleset_source_type"] == "Repository"
            and rule["ruleset_source"] == repo
        ):
            continue
        checks = rule["parameters"]
        if checks["strict_required_status_checks_policy"] is not True or not any(
            check["context"] == "build" and check.get("integration_id") == 15368
            for check in checks["required_status_checks"]
        ):
            continue
        # The effective branch rules do not include bypass actors.
        ruleset = api(f"{prefix}/rulesets/{rule['ruleset_id']}")
        if ruleset["enforcement"] == "active" and ruleset.get("bypass_actors") == []:
            return
    raise ValueError(
        "main must have an active repository ruleset requiring the GitHub Actions build check "
        "and up-to-date branches, with a verifiably empty bypass list"
    )


def require_pr(pr, repo, base_sha, head_sha=None):
    head, base = pr["head"], pr["base"]
    sha = head["sha"]
    if not (
        pr["state"] == "open" and not pr["draft"]
        and pr["title"].startswith("[日次情報更新]")
        and base["ref"] == "main" and base["sha"] == base_sha
        and base["repo"]["full_name"] == repo
        and head["repo"] and head["repo"]["full_name"] == repo
        and re.fullmatch(r"[0-9a-f]{40}", sha)
        and (head_sha is None or sha == head_sha)
    ):
        raise ValueError("PR or its base/head changed; refusing automatic merge")
    return sha


def require_files(pages):
    files = [item for page in pages for item in page]
    allowed = re.compile(r"data/(?:[^/]+\.json|session-notes/[^/]+\.json)")
    if not files or any(
        not allowed.fullmatch(path)
        for item in files
        for path in (item["filename"], item.get("previous_filename", item["filename"]))
    ):
        raise ValueError("PR contains changes outside the permitted data files")


def wait_for_build(repo, number, sha, timeout=1800, interval=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runs = api(
            f"repos/{repo}/actions/workflows/pages.yml/runs"
            f"?event=pull_request&head_sha={sha}&per_page=100"
        )["workflow_runs"]
        matching = [
            run for run in runs
            if run["head_sha"] == sha
            and any(pr["number"] == number for pr in run["pull_requests"])
        ]
        if matching:
            run = max(matching, key=lambda item: item["id"])
            if run["status"] == "completed":
                if run["conclusion"] != "success":
                    raise ValueError(f"Ignite guide failed: {run['conclusion']}")
                return
        time.sleep(interval)
    raise TimeoutError("Timed out waiting for Ignite guide on the update PR")


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    base_sha = os.environ["GITHUB_SHA"]
    number_text = os.environ["PR_NUMBER"]
    if not re.fullmatch(r"[1-9][0-9]*", number_text):
        raise ValueError("Invalid PR number")
    number = int(number_text)
    prefix = f"repos/{repo}"
    require_protection(repo)
    pr_path = f"{prefix}/pulls/{number}"
    sha = require_pr(api(pr_path), repo, base_sha)
    require_files(json.loads(gh("api", "--paginate", "--slurp", f"{pr_path}/files?per_page=100")))
    wait_for_build(repo, number, sha)
    require_protection(repo)
    require_pr(api(pr_path), repo, base_sha, sha)
    gh("pr", "merge", number_text, "--repo", repo, "--squash", "--match-head-commit", sha)
    print(f"Merged daily update PR #{number} at {sha}")


if __name__ == "__main__":
    main()
