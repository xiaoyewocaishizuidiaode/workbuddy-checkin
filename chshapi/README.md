# chshapi（New API）每日自动签到

站点：https://api.chshapi.org/profile

## 重要：不要只复制 session

该站已升级鉴权（Access JWT + refresh cookie）。  
**只复制 `session` 会 401**（你遇到的就是这个）。

浏览器 Cookies 里通常有两行：

| Name | 要不要 |
|------|--------|
| `session` | 可选 |
| **`new_api_refresh`** | **必须**（点这一行，复制完整 Value） |

## 获取 new_api_refresh

1. 登录 https://api.chshapi.org/profile  
2. `F12` → **Application** → **Cookies** → `https://api.chshapi.org`  
3. 点击 **`new_api_refresh`**（不是 session）  
4. 复制 Value 全文  

或在已登录页面的 Console 执行（HttpOnly 时可能读不到，仍以 Application 面板为准）：

```javascript
// HttpOnly cookie 无法用 JS 读取，请用 Application 面板复制 new_api_refresh
```

## 本地测试

```bash
cd chshapi
copy config.example.json config.json
# 填写 refresh = new_api_refresh 的值
python checkin.py
```

成功标志：`[ok] 签到成功` 或 `[ok] 今日已签到`

## GitHub Actions Secrets

| Secret | 说明 |
|--------|------|
| `CHSHAPI_REFRESH` | `new_api_refresh` 的值（可用，但会轮换） |
| `CHSHAPI_ACCESS_TOKEN` | 更推荐：个人中心生成的长期系统访问令牌 |
| `CHSHAPI_BASE_URL` | 可选，默认 `https://api.chshapi.org` |
| `CHSHAPI_SESSION` | 可选 |

定时：每天北京时间 **08:00**（`.github/workflows/chshapi-checkin.yml`）

> 说明：每次 refresh 会轮换 `new_api_refresh`。长期挂 Actions 更建议在网页个人设置生成 **系统访问令牌**，填到 `CHSHAPI_ACCESS_TOKEN`。
