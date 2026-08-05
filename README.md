# WorkBuddy 云端每日签到

用 **GitHub Actions** 每天定时调用 WorkBuddy 签到接口。纯 Python 标准库，无第三方依赖，**不含微信推送**。

## 文件说明

| 文件 | 说明 |
|------|------|
| `checkin.py` | 签到脚本 |
| `config.json` | 仅本地使用（已加入 `.gitignore`，**不要提交**） |
| `config.example.json` | 配置模板 |
| `.github/workflows/checkin.yml` | WorkBuddy：GitHub Actions（每天北京时间 09:05） |
| `chshapi/` | New API 站点 [api.chshapi.org](https://api.chshapi.org/profile) 每日打卡 |
| `.github/workflows/chshapi-checkin.yml` | chshapi：每天北京时间 08:00 |

## 1. 获取 accessToken

WorkBuddy 登录后，本地会保存登录态：

- **Windows**：`%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`
- **macOS**：`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`

打开文件，取 `auth.accessToken`（建议同时带上 `account.uid`、`auth.domain`）。

本地可写入 `config.json`：

```json
{
  "access_token": "eyJhbGc...",
  "account_name": "你的昵称",
  "uid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "domain": "www.codebuddy.cn",
  "enterprise_id": ""
}
```

云端请用 GitHub Secrets（见下文），不要把 token 提交进仓库。

签到接口：`https://www.codebuddy.cn/v2/billing/meter/daily-checkin`（POST）。

## 2. 本地测试

```bash
python checkin.py
```

看到「签到成功」或「今日已签到」即可。

## 3. 部署到 GitHub Actions（推荐）

### 3.1 推送代码

创建 **私有**仓库（推荐），推送本目录（不含 `config.json`）。

### 3.2 配置 Secrets

仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**：

| Secret 名称 | 必填 | 说明 |
|-------------|------|------|
| `WORKBUDDY_ACCESS_TOKEN` | 是 | 本地 auth 里的 `accessToken` |
| `WORKBUDDY_ACCOUNT_NAME` | 否 | 账号昵称，仅用于日志 |
| `WORKBUDDY_UID` | 建议 | `account.uid` |
| `WORKBUDDY_DOMAIN` | 否 | 默认 `www.codebuddy.cn` |
| `WORKBUDDY_ENTERPRISE_ID` | 否 | 企业账号才需要 |

### 3.3 手动跑一次

仓库 → **Actions** → **WorkBuddy Daily Checkin** → **Run workflow**。

日志出现 `[ok] 签到成功` 或 `今日已签到` 即成功。之后每天北京时间 **09:05** 自动跑（cron：`5 1 * * *` UTC）。

### 3.4 Token 过期后

重新从本地 auth 文件复制 token，到 GitHub Secrets 里更新 `WORKBUDDY_ACCESS_TOKEN` 即可，**不用改代码**。

## 4. 额度说明

GitHub Free 私有仓每月约有 **2000 Actions 分钟**；本任务每天约 1～2 分钟，完全够用。公开仓标准 runner 仍免费，但 token 仍须放 Secrets，切勿写进代码。

## 安全提醒

- 优先用 **Secrets**，不要把 `config.json` 推到任何公开仓库
- `accessToken` 等同登录态，勿分享
