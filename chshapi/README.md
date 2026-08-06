# New API 多站点每日签到

已接入：

| 站点 | 地址 | 说明 |
|------|------|------|
| chshapi | https://api.chshapi.org | 新版鉴权，长期 access_token |
| sudobug | https://sudobug.top | 旧版，需 access_token + user_id |
| hcnsec | https://api.hcnsec.cn | 旧版，需 access_token + user_id |
| hcnsec2 | https://api.hcnsec.cn | 同站第二账号，Secrets 用 `HCNSEC2_*` |

均已确认 `checkin_enabled=true`。同一站点可配多个账号（如 hcnsec / hcnsec2）。

## 获取凭证（每个站各做一次）

### 新版（chshapi）
1. 登录 → 个人中心生成**系统访问令牌**，或 Cookie 里的 `new_api_refresh`

### 旧版（sudobug / hcnsec）
1. 登录 [https://api.hcnsec.cn/profile](https://api.hcnsec.cn/profile)（或对应站点）
2. 个人中心复制**系统访问令牌**（access_token）
3. F12 Console 执行：`JSON.parse(localStorage.getItem('user')).id` 得到 **user_id**

填到 `config.json`（参考 `config.example.json`）。

本地测试：

```bash
python chshapi/checkin.py
```

## GitHub Secrets

| Secret | 站点 |
|--------|------|
| `CHSHAPI_ACCESS_TOKEN` | chshapi |
| `SUDOBUG_ACCESS_TOKEN` / `SUDOBUG_USER_ID` | sudobug |
| `HCNSEC_ACCESS_TOKEN` / `HCNSEC_USER_ID` | hcnsec 账号1 |
| `HCNSEC2_ACCESS_TOKEN` / `HCNSEC2_USER_ID` | hcnsec 账号2 |
| `NEWAPI_SITES` | 可选，整份 JSON 覆盖 |

定时：每天北京时间 **08:00**
