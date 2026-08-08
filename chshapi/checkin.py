#!/usr/bin/env python3
"""
New API 多站点每日签到

支持站点示例：
  - https://api.chshapi.org
  - https://sudobug.top
  - https://api.hcnsec.cn

鉴权（新版 New API）：
  1) Cookie new_api_refresh -> POST /api/user/auth/refresh
  2) Authorization: Bearer <access_token>
  3) GET/POST /api/user/checkin

推荐上云使用长期 access_token（个人中心系统访问令牌 / GET /api/user/token）。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REQUEST_TIMEOUT = 20
_CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
_TZ = timezone(timedelta(hours=8))


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), flush=True)


def _normalize_site(raw: dict[str, Any], default_name: str = "site") -> dict[str, Any] | None:
    base = str(raw.get("base_url") or raw.get("url") or "").strip().rstrip("/")
    access_token = str(raw.get("access_token") or "").strip() or None
    refresh = str(raw.get("refresh") or raw.get("new_api_refresh") or "").strip() or None
    session = str(raw.get("session") or "").strip() or None
    user_id = str(raw.get("user_id") or raw.get("uid") or "").strip() or None
    name = str(raw.get("name") or default_name).strip() or default_name
    if not base:
        return None
    # 新版：refresh/access_token；旧版：完整 session 也可
    if not access_token and not refresh and not session:
        return None
    return {
        "name": name,
        "base_url": base,
        "access_token": access_token,
        "refresh": refresh,
        "session": session,
        "user_id": user_id,
    }


def _site_from_prefix(prefix: str, default_url: str, default_name: str) -> dict[str, Any] | None:
    base = os.environ.get(f"{prefix}_BASE_URL", "").strip() or default_url
    access = os.environ.get(f"{prefix}_ACCESS_TOKEN", "").strip()
    refresh = os.environ.get(f"{prefix}_REFRESH", "").strip()
    session = os.environ.get(f"{prefix}_SESSION", "").strip()
    user_id = os.environ.get(f"{prefix}_USER_ID", "").strip()
    if not access and not refresh and not session:
        return None
    return _normalize_site(
        {
            "name": default_name,
            "base_url": base,
            "access_token": access,
            "refresh": refresh,
            "session": session,
            "user_id": user_id,
        },
        default_name=default_name,
    )


def load_sites() -> list[dict[str, Any]]:
    """
    加载站点列表，优先级：
      1) 环境变量 NEWAPI_SITES = JSON 数组
      2) config.json 的 sites 数组
      3) config.json 单站点对象（兼容旧格式）
      4) 环境变量 CHSHAPI_* / SUDOBUG_* / SUDOBUG2_* / HCNSEC_* / HCNSEC2_*
    """
    sites: list[dict[str, Any]] = []
    # 同站多账号：SUDOBUG2 / HCNSEC2 等与主账号并列签到
    _PREFIX_SITES = (
        ("CHSHAPI", "https://api.chshapi.org", "chshapi"),
        ("SUDOBUG", "https://sudobug.top", "sudobug"),
        ("SUDOBUG2", "https://sudobug.top", "sudobug2"),
        ("HCNSEC", "https://api.hcnsec.cn", "hcnsec"),
        ("HCNSEC2", "https://api.hcnsec.cn", "hcnsec2"),
    )

    env_sites = os.environ.get("NEWAPI_SITES", "").strip()
    if env_sites:
        try:
            arr = json.loads(env_sites)
            if isinstance(arr, list):
                for i, item in enumerate(arr):
                    if isinstance(item, dict):
                        s = _normalize_site(item, default_name=f"site{i+1}")
                        if s:
                            sites.append(s)
        except Exception as e:
            log(f"[!] 解析 NEWAPI_SITES 失败: {e}")

    file_cfg: dict[str, Any] = {}
    if _CONFIG_FILE.exists():
        try:
            file_cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"[!] 读取 config.json 失败: {e}")

    if not sites and isinstance(file_cfg.get("sites"), list):
        for i, item in enumerate(file_cfg["sites"]):
            if isinstance(item, dict):
                s = _normalize_site(item, default_name=item.get("name") or f"site{i+1}")
                if s:
                    sites.append(s)

    if not sites and file_cfg.get("base_url"):
        s = _normalize_site(file_cfg, default_name="default")
        if s:
            sites.append(s)

    if not sites:
        for prefix, url, name in _PREFIX_SITES:
            s = _site_from_prefix(prefix, url, name)
            if s:
                sites.append(s)

    # 环境变量可覆盖同名站点的 token（方便 GitHub Secrets）
    overrides = {
        name: _site_from_prefix(prefix, url, name) for prefix, url, name in _PREFIX_SITES
    }
    by_name = {s["name"]: s for s in sites}
    for name, ov in overrides.items():
        if not ov:
            continue
        if name in by_name:
            # secrets 优先覆盖 access_token/refresh
            cur = by_name[name]
            if ov.get("access_token"):
                cur["access_token"] = ov["access_token"]
            if ov.get("refresh"):
                cur["refresh"] = ov["refresh"]
            if ov.get("session"):
                cur["session"] = ov["session"]
            if ov.get("user_id"):
                cur["user_id"] = ov["user_id"]
            if ov.get("base_url"):
                cur["base_url"] = ov["base_url"]
        else:
            sites.append(ov)
            by_name[name] = ov

    return sites


def parse_set_cookie(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    raw_list = []
    if hasattr(headers, "get_all"):
        raw_list = headers.get_all("Set-Cookie") or []
    elif "Set-Cookie" in headers:
        raw_list = [headers["Set-Cookie"]]
    for item in raw_list:
        first = item.split(";", 1)[0]
        if "=" not in first:
            continue
        name, value = first.split("=", 1)
        out[name.strip()] = value.strip()
    return out


class Client:
    def __init__(self, cfg: dict):
        self.name = cfg.get("name") or "site"
        self.base = cfg["base_url"]
        self.access_token = cfg.get("access_token")
        self.refresh = cfg.get("refresh")
        self.session = cfg.get("session")
        self.user_id = str(cfg["user_id"]) if cfg.get("user_id") not in (None, "") else None

    def _common_headers(self) -> dict[str, str]:
        headers = {
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
        if self.user_id:
            headers["New-Api-User"] = self.user_id
            headers["new-api-user"] = self.user_id
        return headers

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
                return payload, parse_set_cookie(resp.headers)
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
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        if (
            data.get("checked_in_today")
            or data.get("today_checked_in")
            or data.get("checked_in")
            or stats.get("checked_in_today")
        ):
            return True
    return False


def persist_site_update(site_name: str, client: Client, long_token: str | None = None) -> None:
    """更新 config.json 中对应站点的 refresh/access_token。"""
    root: dict[str, Any] = {"sites": []}
    if _CONFIG_FILE.exists():
        try:
            loaded = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded.get("sites"), list):
                root = loaded
            elif loaded.get("base_url"):
                # 旧单站点格式迁移
                old = _normalize_site(loaded, default_name="chshapi")
                root = {"sites": [old] if old else []}
        except Exception:
            pass

    sites = root.get("sites") if isinstance(root.get("sites"), list) else []
    found = False
    for item in sites:
        if not isinstance(item, dict):
            continue
        if item.get("name") == site_name or item.get("base_url") == client.base:
            item["name"] = site_name
            item["base_url"] = client.base
            if client.refresh:
                item["refresh"] = client.refresh
            if client.session:
                item["session"] = client.session
            if client.user_id:
                item["user_id"] = client.user_id
            if long_token:
                item["access_token"] = long_token
            elif client.access_token and not str(item.get("access_token") or "").strip():
                pass
            found = True
            break
    if not found:
        sites.append(
            {
                "name": site_name,
                "base_url": client.base,
                "refresh": client.refresh or "",
                "session": client.session or "",
                "access_token": long_token or client.access_token or "",
                "user_id": client.user_id or "",
            }
        )
    root["sites"] = sites
    try:
        _CONFIG_FILE.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log("   已更新本地 config.json")
    except Exception as e:
        log(f"   [!] 写回 config.json 失败: {e}")


def ensure_access_token(client: Client) -> bool:
    if client.access_token:
        log("步骤 1/4: 使用已配置的 access_token")
        return True

    # 旧版 New API：没有 /api/user/auth/refresh，仅 session cookie 即可
    if client.session and not client.refresh:
        log("步骤 1/4: 尝试旧版 session Cookie 鉴权 ...")
        payload, _ = client.request("GET", "/api/user/self", use_bearer=False)
        if is_success(payload):
            user = payload.get("data") or {}
            log(f"   session 有效: user_id={user.get('id')}, name={user.get('username')}")
            return True
        log("   session 无效或未完整复制，继续尝试 refresh ...")

    if not client.refresh:
        log("[x] 缺少可用凭证：请提供完整 session，或系统访问令牌 access_token，或 new_api_refresh")
        return False

    log("步骤 1/4: POST /api/user/auth/refresh 换取 access_token ...")
    payload, set_cookies = client.request("POST", "/api/user/auth/refresh", use_bearer=False)
    if not is_success(payload):
        log("[x] refresh 失败。请确认 new_api_refresh 完整且未过期。")
        return False
    data = payload.get("data") or {}
    token = data.get("access_token")
    if not token:
        log(f"[x] refresh 响应无 access_token: {json.dumps(payload, ensure_ascii=False)[:300]}")
        return False
    client.access_token = token
    new_refresh = set_cookies.get("new_api_refresh")
    if new_refresh:
        client.refresh = new_refresh
        log("   refresh cookie 已轮换")
        persist_site_update(client.name, client)
    user = data.get("user") or {}
    log(f"   刷新成功: user_id={user.get('id')}, name={user.get('username') or user.get('display_name')}")
    return True


def try_issue_long_token(client: Client) -> str | None:
    log("附加: GET /api/user/token 生成长期 access_token ...")
    payload, _ = client.request("GET", "/api/user/token")
    if not is_success(payload):
        log("   生成长期 token 失败（可忽略）")
        return None
    token = payload.get("data")
    if not isinstance(token, str) or not token:
        return None
    log(f"   长期 token 已生成，长度={len(token)}")
    return token


def checkin_one(site: dict[str, Any]) -> bool:
    name = site["name"]
    log("=" * 56)
    log(f"  [{name}] New API 签到 --- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 56)
    log(f"   base_url={site['base_url']}")

    client = Client(site)
    if not ensure_access_token(client):
        return False

    # 仅首次（无长期 token）时生成，避免作废 Secrets
    prefix = name.upper().replace("-", "_")
    had_access_env = bool(
        os.environ.get(f"{prefix}_ACCESS_TOKEN", "").strip()
        or os.environ.get("CHSHAPI_ACCESS_TOKEN" if name == "chshapi" else "", "").strip()
        or os.environ.get("SUDOBUG_ACCESS_TOKEN" if name == "sudobug" else "", "").strip()
    )
    had_access_cfg = bool(site.get("access_token"))
    if client.refresh and not had_access_env and not had_access_cfg:
        long_token = try_issue_long_token(client)
        if long_token:
            client.access_token = long_token
            persist_site_update(name, client, long_token=long_token)
            log("   已写入长期 access_token 到 config.json")
    else:
        log("步骤 1.5/4: 跳过重新生成长期 token")

    log("步骤 2/4: GET /api/user/self ...")
    me, _ = client.request("GET", "/api/user/self", use_bearer=bool(client.access_token))
    if (
        not is_success(me)
        and client.access_token
        and not client.user_id
        and isinstance(me, dict)
        and "New-Api-User" in str(me.get("message") or "")
    ):
        log("[!] 该站需要 New-Api-User。请在配置里填 user_id")
        log("    浏览器 Console 执行: JSON.parse(localStorage.getItem('user')).id")
        return False
    if not is_success(me) and client.session and client.access_token:
        me, _ = client.request("GET", "/api/user/self", use_bearer=False)
    if not is_success(me):
        log("[x] /api/user/self 失败，token/session/user_id 无效")
        return False
    user = me.get("data") or {}
    uid = user.get("id")
    if uid is not None:
        client.user_id = str(uid)
    log(f"   登录用户: id={uid}, username={user.get('username')}")

    month = datetime.now(_TZ).strftime("%Y-%m")
    status_path = "/api/user/checkin?" + urllib.parse.urlencode({"month": month})
    log(f"步骤 3/4: GET {status_path} ...")
    status, _ = client.request("GET", status_path, use_bearer=bool(client.access_token))
    if already_checked(status):
        log(f"[ok] [{name}] 今日已签到（状态接口）")
        persist_site_update(name, client)
        return True
    if is_success(status) and isinstance(status.get("data"), dict):
        data = status["data"]
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        log(
            f"   checked_in_today={data.get('checked_in_today') or stats.get('checked_in_today')}"
        )

    log("步骤 4/4: POST /api/user/checkin ...")
    result, _ = client.request("POST", "/api/user/checkin", use_bearer=bool(client.access_token))
    if already_checked(result):
        log(f"[ok] [{name}] 今日已签到")
        persist_site_update(name, client)
        return True
    if is_success(result):
        log(f"[ok] [{name}] 签到成功! {json.dumps(result, ensure_ascii=False)[:400]}")
        persist_site_update(name, client)
        return True
    log(f"[x] [{name}] 签到失败: {json.dumps(result, ensure_ascii=False) if result else '无响应'}")
    return False


def request_with_user_header(
    client: Client,
    method: str,
    path: str,
    user_id: str,
    data: bytes | None = None,
) -> dict | None:
    # 保留兼容；主流程已通过 Client.user_id 自动带 header
    client.user_id = user_id
    payload, _ = client.request(method, path, use_bearer=bool(client.access_token), data=data)
    return payload


def main() -> int:
    sites = load_sites()
    if not sites:
        log("[x] 未配置任何站点。请在 config.json 的 sites 中配置，或设置 CHSHAPI_*/SUDOBUG_*/SUDOBUG2_*/HCNSEC_*/HCNSEC2_* / NEWAPI_SITES")
        return 1

    log(f"共 {len(sites)} 个站点待签到: {', '.join(s['name'] for s in sites)}")
    results = []
    for site in sites:
        ok = checkin_one(site)
        results.append((site["name"], ok))
        log("")

    log("=" * 56)
    log("汇总:")
    failed = 0
    for name, ok in results:
        log(f"  - {name}: {'OK' if ok else 'FAIL'}")
        if not ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
