# New API 多站点每日签到

已接入：

| 站点 | 地址 | 说明 |
|------|------|------|
| chshapi | https://api.chshapi.org | 已配置 |
| sudobug | https://sudobug.top | 需提供 `new_api_refresh` |

两个站都已确认 `checkin_enabled=true`。

## 获取凭证（每个站各做一次）

1. 浏览器登录对应站点 `/profile`
2. F12 → Application → Cookies
3. 复制 **`new_api_refresh`**（不要只复制 session）

填到 `config.json`：

```json
{
  "sites": [
    {
      "name": "chshapi",
      "base_url": "https://api.chshapi.org",
      "access_token": "长期令牌",
      "refresh": "",
      "session": ""
    },
    {
      "name": "sudobug",
      "base_url": "https://sudobug.top",
      "access_token": "",
      "refresh": "这里贴 new_api_refresh",
      "session": ""
    }
  ]
}
```

本地测试：

```bash
python chshapi/checkin.py
```

首次用 refresh 跑通后，脚本可生成长期 `access_token`，上云更稳。

## GitHub Secrets

| Secret | 站点 |
|--------|------|
| `CHSHAPI_ACCESS_TOKEN` | chshapi（已有） |
| `SUDOBUG_ACCESS_TOKEN` | sudobug（推荐） |
| `SUDOBUG_REFRESH` | sudobug 临时也行 |
| `NEWAPI_SITES` | 可选，整份 JSON 覆盖 |

定时：每天北京时间 **08:00**
