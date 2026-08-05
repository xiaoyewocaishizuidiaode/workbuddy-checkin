#!/usr/bin/env python3
"""
New API 站点每日签到（api.chshapi.org）

该站已升级鉴权：面板接口不再认单纯 session Cookie。
正确流程：
  1) Cookie new_api_refresh  -> POST /api/user/auth/refresh
  2) 拿到 data.access_token
  3) Authorization: Bearer <access_token>
  4) GET/POST /api/user/checkin

也支持直接配置长期 access_token（个人中心生成的系统访问令牌）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.chshapi.org"
REQUEST_TIMEOUT = 20
_CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
_TZ = timezone(timedelta(hours=8))


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), flush=True)


def load_config() -> dict | None:
    """
    环境变量优先：
      CHSHAPI_BASE_URL
      CHSHAPI_ACCESS_TOKEN   # 长期令牌（推荐上云）
      CHSHAPI_REFRESH        # new_api_refresh cookie
      CHSHAPI_SESSION        # 可选，旧 session cookie
    """
    file_cfg: dict[str, Any] = {}
    if _CONFIG_FILE.exists():
        try:
            file_cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"[!] 读取 config.json 失败: {e}")

    def pick(*keys: str, default: str = "") -> str:
        for k in keys:
            v = os.environ.get(k, "").strip()
            if v:
                return v
        for k in keys:
            # map ENV style to json keys
            jk = k.lower().replace("chshapi_", "")
            v = str(file_cfg.get(jk) or file_cfg.get(k) or "").strip()
            if v:
                return v
        return default

    base_url = pick("CHSHAPI_BASE_URL", "base_url", default=DEFAULT_BASE_URL).rstrip("/")
    access_token = pick("CHSHAPI_ACCESS_TOKEN", "access_token")
    refresh = pick("CHSHAPI_REFRESH", "refresh", "new_api_refresh")
    session = pick("CHSHAPI_SESSION", "session")

    if not access_token and not refresh:
        log("[x] 需要配置 CHSHAPI_REFRESH(new_api_refresh) 或 CHSHAPI_ACCESS_TOKEN")
        log("    仅复制 session 不够：该站已改为 Access JWT + refresh cookie 鉴权")
        return None

    return {
        "base_url": base_url or DEFAULT_BASE_URL,
        "access_token": access_token or None,
        "refresh": refresh or None,
        "session": session or None,
    }


def parse_set_cookie(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    raw_list = []
    if hasattr(headers, "get_all"):
        raw_list = headers.get_all("Set-Cookie") or []
    elif "Set-Cookie" in headers:
        raw_list = [headers["Set-Cookie"]]
    for item in raw_list:
        # name=value; Path=...
        first = item.split(";", 1)[0]
        if "=" not in first:
            continue
        name, value = first.split("=", 1)
        out[name.strip()] = value.strip()
    return out


class Client:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base = cfg["base_url"]
        self.access_token = cfg.get("access_token")
        self.refresh = cfg.get("refresh")
        self.session = cfg.get("session")

    def _common_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Origin": self.base,
            "Referer": f"{self.base}/profile",
        }

    def _cookie_header(self) -> str:
        parts = []
        if self.session:
            parts.append(f"session={self.session}")
        if self.refresh:
            parts.append(f"new_api_refresh={self.refresh}")
        return "; ".join(parts)

    def request(
        self,
        method: str,
        path: str,
        *,
        use_bearer: bool = True,
        data: bytes | None = None,
    ) -> tuple[dict | None, dict[str, str]]:
        headers = self._common_headers()
        cookie = self._cookie_header()
        if cookie:
            headers["Cookie"] = cookie
        if use_bearer and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        if method.upper() == "POST" and data is None:
            data = b"{}"

        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method.upper(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                payload = json.loads(raw) if raw else {}
                set_cookies = parse_set_cookie(resp.headers)
                return payload, set_cookies
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            log(f"   HTTP {e.code}: {e.reason} {err_body[:300]}")
            set_cookies = parse_set_cookie(e.headers) if e.headers else {}
            try:
                return (json.loads(err_body) if err_body else {"_http": e.code}), set_cookies
            except Exception:
                return {"_http": e.code, "message": err_body[:200]}, set_cookies
        except Exception as e:
            log(f"   请求失败: {e}")
            return None, {}


def is_success(payload: dict | None) -> bool:
    return isinstance(payload, dict) and payload.get("success") is True


def already_checked(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    msg = str(payload.get("message") or payload.get("msg") or "")
    if any(x in msg for x in ("已签到", "已经签到", "重复签到", "already", "Already")):
        return True
    data = payload.get("data")
    if isinstance(data, dict):
        if data.get("checked_in_today") or data.get("today_checked_in") or data.get("checked_in"):
            return True
    return False


def ensure_access_token(client: Client) -> bool:
    if client.access_token:
        log("步骤 1/4: 使用已配置的 access_token")
        return True

    if not client.refresh:
        log("[x] 缺少 new_api_refresh，无法换取 access_token")
        return False

    log("步骤 1/4: POST /api/user/auth/refresh 换取 access_token ...")
    payload, set_cookies = client.request("POST", "/api/user/auth/refresh", use_bearer=False)
    if not is_success(payload):
        log("[x] refresh 失败。请确认复制的是 Cookie「new_api_refresh」完整值，且未过期。")
        return False

    data = payload.get("data") or {}
    token = data.get("access_token")
    if not token:
        log(f"[x] refresh 响应无 access_token: {json.dumps(payload, ensure_ascii=False)[:300]}")
        return False

    client.access_token = token
    # refresh 会轮换，必须落盘，否则下次失效
    new_refresh = set_cookies.get("new_api_refresh")
    if new_refresh:
        client.refresh = new_refresh
        log("   refresh cookie 已轮换")
        persist_config_update(client)
    user = data.get("user") or {}
    log(f"   刷新成功: user_id={user.get('id')}, name={user.get('username') or user.get('display_name')}")
    log(f"   access_expires_at={data.get('access_expires_at')}")
    return True


def persist_config_update(client: Client) -> None:
    """把轮换后的 refresh / 可选长期 token 写回本地 config.json。"""
    cfg: dict[str, Any] = {}
    if _CONFIG_FILE.exists():
        try:
            cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg["base_url"] = client.base
    if client.refresh:
        cfg["refresh"] = client.refresh
    if client.session:
        cfg["session"] = client.session
    # 不把短期 JWT 当长期 token 写入 access_token 字段
    if "access_token" not in cfg:
        cfg["access_token"] = ""
    try:
        _CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log("   已更新本地 config.json 中的 refresh")
    except Exception as e:
        log(f"   [!] 写回 config.json 失败: {e}")


def try_issue_long_token(client: Client) -> str | None:
    """调用 GET /api/user/token 生成可长期使用的系统访问令牌。"""
    log("附加: GET /api/user/token 生成长期 access_token ...")
    payload, _ = client.request("GET", "/api/user/token")
    if not is_success(payload):
        log("   生成长期 token 失败（可忽略，仍可用 refresh）")
        return None
    token = payload.get("data")
    if not isinstance(token, str) or not token:
        log(f"   响应异常: {json.dumps(payload, ensure_ascii=False)[:200]}")
        return None
    log(f"   长期 token 已生成，长度={len(token)}")
    return token


def checkin() -> bool:
    log("=" * 56)
    log(f"  chshapi 每日签到 --- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 56)

    cfg = load_config()
    if not cfg:
        return False
    log(f"   base_url={cfg['base_url']}")

    client = Client(cfg)
    if not ensure_access_token(client):
        return False

    # 尽量生成长期令牌，方便 GitHub Actions（避免 refresh 轮换麻烦）
    long_token = try_issue_long_token(client)
    if long_token:
        cfg_path_data: dict[str, Any] = {}
        if _CONFIG_FILE.exists():
            try:
                cfg_path_data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                cfg_path_data = {}
        cfg_path_data["access_token"] = long_token
        if client.refresh:
            cfg_path_data["refresh"] = client.refresh
        cfg_path_data["base_url"] = client.base
        try:
            _CONFIG_FILE.write_text(
                json.dumps(cfg_path_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            log("   已写入 config.json 的 access_token（可用于 GitHub Secrets: CHSHAPI_ACCESS_TOKEN）")
        except Exception as e:
            log(f"   [!] 保存长期 token 失败: {e}")

    log("步骤 2/4: GET /api/user/self 验证登录 ...")
    me, _ = client.request("GET", "/api/user/self")
    if not is_success(me):
        log("[x] /api/user/self 失败，token 无效")
        return False
    user = me.get("data") or {}
    log(f"   登录用户: id={user.get('id')}, username={user.get('username')}")

    month = datetime.now(_TZ).strftime("%Y-%m")
    status_path = "/api/user/checkin?" + urllib.parse.urlencode({"month": month})
    log(f"步骤 3/4: GET {status_path} ...")
    status, _ = client.request("GET", status_path)
    if already_checked(status):
        log("[ok] 今日已签到（状态接口）")
        return True
    if is_success(status) and isinstance(status.get("data"), dict):
        data = status["data"]
        log(
            f"   checked_in_today={data.get('checked_in_today') or data.get('today_checked_in')}"
        )

    log("步骤 4/4: POST /api/user/checkin ...")
    result, _ = client.request("POST", "/api/user/checkin")
    if already_checked(result):
        log("[ok] 今日已签到")
        return True
    if is_success(result):
        log(f"[ok] 签到成功! {json.dumps(result, ensure_ascii=False)[:500]}")
        return True

    log(f"[x] 签到失败: {json.dumps(result, ensure_ascii=False) if result else '无响应'}")
    return False


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(0 if checkin() else 1)
