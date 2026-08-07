#!/usr/bin/env python3
"""
用 cron-job.org API 创建 / 更新「触发 GitHub Actions」的定时任务。

策略：
  08:00  主签到（WorkBuddy + NewAPI）
  09:00  看门狗补签（再触发一次；已签到会被脚本当成成功）

前置：
  1) https://cron-job.org Settings 生成 API Key
  2) GitHub PAT（Fine-grained：目标仓库 Actions=Read and write）

用法（PowerShell）：
  $env:CRONJOB_ORG_API_KEY = "..."
  $env:GITHUB_PAT = "..."
  python scripts/setup_cronjob_org.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://api.cron-job.org"
OWNER = os.environ.get("GITHUB_OWNER", "xiaoyewocaishizuidiaode").strip()
REPO = os.environ.get("GITHUB_REPO", "workbuddy-checkin").strip()
TZ = os.environ.get("TIMEZONE", "Asia/Shanghai").strip()

# (title, workflow_file, hour, minute)
JOB_SPECS = [
    ("WorkBuddy Daily Checkin (external)", "checkin.yml", 8, 0),
    ("NewAPI Daily Checkin (external)", "chshapi-checkin.yml", 8, 0),
    ("WorkBuddy Watchdog (external)", "checkin.yml", 9, 0),
    ("NewAPI Watchdog (external)", "chshapi-checkin.yml", 9, 0),
]


def api(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "workbuddy-cron-setup/1.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} {path}: {body[:500]}") from e


def make_job(title: str, workflow_file: str, hour: int, minute: int, github_pat: str) -> dict:
    url = (
        f"https://api.github.com/repos/{OWNER}/{REPO}"
        f"/actions/workflows/{workflow_file}/dispatches"
    )
    return {
        "job": {
            "enabled": True,
            "title": title,
            "url": url,
            "requestMethod": 1,  # POST
            "saveResponses": True,
            "schedule": {
                "timezone": TZ,
                "expiresAt": 0,
                "hours": [hour],
                "minutes": [minute],
                "mdays": [-1],
                "months": [-1],
                "wdays": [-1],
            },
            "extendedData": {
                "headers": {
                    "Authorization": f"Bearer {github_pat}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "Content-Type": "application/json",
                    "User-Agent": "cron-job-org-workbuddy",
                },
                "body": json.dumps({"ref": "main"}),
            },
        }
    }


def find_existing(jobs: list[dict], title: str) -> dict | None:
    for j in jobs:
        if j.get("title") == title:
            return j
    return None


def main() -> int:
    cron_key = os.environ.get("CRONJOB_ORG_API_KEY", "").strip()
    github_pat = os.environ.get("GITHUB_PAT", "").strip()
    if not cron_key or not github_pat:
        print(
            "请设置环境变量:\n"
            "  CRONJOB_ORG_API_KEY  — cron-job.org Settings 里的 API Key\n"
            "  GITHUB_PAT           — 能触发 Actions 的 GitHub PAT\n",
            file=sys.stderr,
        )
        return 1

    listed = api("GET", "/jobs", cron_key)
    existing = listed.get("jobs") or []

    for title, wf, hour, minute in JOB_SPECS:
        payload = make_job(title, wf, hour, minute, github_pat)
        found = find_existing(existing, title)
        if found:
            job_id = found["jobId"]
            api("PATCH", f"/jobs/{job_id}", cron_key, payload)
            print(f"updated jobId={job_id} title={title} @ {hour:02d}:{minute:02d} {TZ}")
        else:
            result = api("PUT", "/jobs", cron_key, payload)
            print(f"created title={title} @ {hour:02d}:{minute:02d} {TZ} resp={result}")

    print("\n完成。可在 https://console.cron-job.org/ 查看：")
    print("  08:00 主签到 ×2")
    print("  09:00 看门狗补签 ×2")
    print(f"GitHub Actions: https://github.com/{OWNER}/{REPO}/actions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
