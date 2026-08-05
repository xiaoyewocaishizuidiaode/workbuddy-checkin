#!/usr/bin/env python3
"""
WorkBuddy 每日签到脚本
支持本地运行和 GitHub Actions 云端定时运行（无微信推送）

接口参考开源实现：https://www.codebuddy.cn/v2/billing/meter/*
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ─── 配置 ───────────────────────────────────────────────
API_BASE = "https://www.codebuddy.cn"
CHECKIN_STATUS_URL = f"{API_BASE}/v2/billing/meter/checkin-status"
DAILY_CHECKIN_URL = f"{API_BASE}/v2/billing/meter/daily-checkin"
REQUEST_TIMEOUT = 20

_WIN_AUTH_FILE = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "CodeBuddyExtension"
    / "Data/Public/auth/workbuddy-desktop.info"
)
_MAC_AUTH_FILE = (
    Path.home()
    / "Library/Application Support/CodeBuddyExtension"
    / "Data/Public/auth/workbuddy-desktop.info"
)
_CLOUD_CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def log(msg: str) -> None:
    # Windows 控制台默认 GBK，避免 emoji 导致崩溃
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), flush=True)


def _read_local_auth(auth_file: Path) -> dict | None:
    if not auth_file.exists():
        return None
    try:
        return json.loads(auth_file.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"[!] 读取 auth 文件失败 ({auth_file}): {e}")
        return None


def _creds_from_env() -> dict | None:
    token = os.environ.get("WORKBUDDY_ACCESS_TOKEN", "").strip()
    if not token:
        return None
    return {
        "access_token": token,
        "account_name": os.environ.get("WORKBUDDY_ACCOUNT_NAME", "环境变量账号"),
        "uid": os.environ.get("WORKBUDDY_UID", "").strip() or None,
        "domain": os.environ.get("WORKBUDDY_DOMAIN", "www.codebuddy.cn").strip(),
        "enterprise_id": os.environ.get("WORKBUDDY_ENTERPRISE_ID", "").strip() or None,
    }


def _creds_from_config() -> dict | None:
    if not _CLOUD_CONFIG_FILE.exists():
        return None
    try:
        data = json.loads(_CLOUD_CONFIG_FILE.read_text(encoding="utf-8"))
        token = (data.get("access_token") or "").strip()
        if not token:
            return None
        return {
            "access_token": token,
            "account_name": data.get("account_name") or "云端账号",
            "uid": (data.get("uid") or "").strip() or None,
            "domain": (data.get("domain") or "www.codebuddy.cn").strip(),
            "enterprise_id": (data.get("enterprise_id") or "").strip() or None,
        }
    except Exception as e:
        log(f"[!] 读取 config.json 失败: {e}")
        return None


def load_credentials() -> dict | None:
    """
    返回 {access_token, account_name, uid, domain, enterprise_id}
    优先级：CI/环境变量 > config.json > 本地 auth
    """
    # GitHub Actions 等 CI 优先用 Secrets 注入的环境变量
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
        creds = _creds_from_env()
        if creds:
            log(f"   使用环境变量 (账号: {creds['account_name']})")
            return creds

    creds = _creds_from_config()
    if creds:
        log(f"   使用 config.json (账号: {creds['account_name']})")
        return creds

    creds = _creds_from_env()
    if creds:
        log(f"   使用环境变量 (账号: {creds['account_name']})")
        return creds

    for auth_file, label in ((_WIN_AUTH_FILE, "Windows"), (_MAC_AUTH_FILE, "macOS")):
        data = _read_local_auth(auth_file)
        if not data:
            continue
        token = (data.get("auth", {}).get("accessToken") or "").strip()
        if not token:
            log(f"[x] {label} auth 中未找到 accessToken")
            continue
        account = data.get("account") or {}
        creds = {
            "access_token": token,
            "account_name": account.get("nickname") or f"{label}账号",
            "uid": (account.get("uid") or "").strip() or None,
            "domain": (data.get("auth", {}).get("domain") or "www.codebuddy.cn").strip(),
            "enterprise_id": (
                (account.get("enterpriseId") or account.get("enterprise_id") or "").strip() or None
            ),
        }
        log(f"   使用 {label} 本地 auth (账号: {creds['account_name']})")
        return creds

    log("[x] 未找到任何 token 来源，请配置 config.json 或环境变量")
    return None


def _build_headers(creds: dict) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {creds['access_token']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "WorkBuddy-Checkin/1.1",
    }
    if creds.get("uid"):
        headers["X-User-Id"] = creds["uid"]
    if creds.get("domain"):
        headers["X-Domain"] = creds["domain"]
    eid = creds.get("enterprise_id")
    if eid:
        headers["X-Enterprise-Id"] = eid
        headers["X-Tenant-Id"] = eid
    return headers


def _request_json(url: str, creds: dict, method: str = "POST") -> dict | None:
    body = b"{}"
    req = urllib.request.Request(
        url,
        data=body,
        method=method.upper(),
        headers=_build_headers(creds),
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        log(f"   HTTP {e.code}: {e.reason} {err_body[:300]}")
        try:
            return json.loads(err_body) if err_body else None
        except Exception:
            return None
    except Exception as e:
        log(f"   请求失败: {e}")
        return None


def _msg_of(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("message") or payload.get("msg") or "")


def already_checked_in(payload: dict | None) -> bool:
    """接口可能用业务码/文案表示「今日已签」。"""
    if not isinstance(payload, dict):
        return False
    code = payload.get("code")
    msg = _msg_of(payload)
    if code == 10001 or "已签到" in msg or "已经签到" in msg:
        return True
    data = payload.get("data")
    if isinstance(data, dict) and (data.get("today_checked_in") or data.get("checked_in")):
        return True
    return bool(payload.get("today_checked_in") or payload.get("checked_in"))


def unwrap_data(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if code is not None and code not in (0, 200):
        msg = _msg_of(payload) or "unknown"
        log(f"   业务错误 code={code}: {msg}")
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def checkin() -> bool:
    log("=" * 56)
    log(f"  WorkBuddy 每日签到 --- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 56)

    log("步骤 1/3: 获取凭证...")
    creds = load_credentials()
    if not creds:
        return False

    log("步骤 2/3: 查询签到状态...")
    status_raw = _request_json(CHECKIN_STATUS_URL, creds, method="POST")
    if already_checked_in(status_raw):
        log("[ok] 今日已签到，无需重复领取。")
        return True
    status = unwrap_data(status_raw)
    if status is None:
        log("[!] 签到状态查询失败，继续尝试领取...")
    else:
        log(
            f"   active={status.get('active')}, "
            f"today_checked_in={status.get('today_checked_in')}, "
            f"streak_days={status.get('streak_days')}"
        )

    log("步骤 3/3: 领取签到积分...")
    result_raw = _request_json(DAILY_CHECKIN_URL, creds, method="POST")
    if already_checked_in(result_raw):
        log("[ok] 今日已签到。")
        return True

    result = unwrap_data(result_raw)
    if result is None:
        log("[x] 签到失败，请检查 token 是否过期。")
        return False

    success = result.get("success", True)
    credit = result.get("credit", result.get("today_credit", result.get("points")))
    streak = result.get("streak_days")
    message = result.get("message") or ""
    if success is False:
        log(f"[!] 领取未成功: {message or result}")
        return False

    log(f"[ok] 签到成功! credit={credit}, streak_days={streak} {message}")
    return True


if __name__ == "__main__":
    # 尽量让 stdout 用 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(0 if checkin() else 1)
