# 用 cron-job.org 准时触发 GitHub Actions 签到（含看门狗）

GitHub 自带的 `schedule` 经常晚几小时。做法是：

```text
08:00  cron-job.org → 主签到（WorkBuddy + NewAPI）
09:00  cron-job.org → 看门狗再触发一次（未签则补签；已签则「今日已签到」）
        ↓ POST workflow_dispatch
GitHub Actions（跑原来的签到脚本）
```

签到逻辑、Secrets 都还在 GitHub，外部只负责「到点点一下 Run」。

---

## 你需要准备两样东西

### 1）GitHub PAT

打开：[https://github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)

推荐 **Fine-grained token**：

| 项 | 选 |
|----|----|
| Repository access | 只选 `workbuddy-checkin` |
| Permissions → **Repository permissions** → Actions | **Read and write** |
| Permissions → Contents | Read-only（建议） |
| Account permissions | 保持 0，不用加 |

Classic token 则勾选 `repo` + `workflow`。

### 2）cron-job.org 账号 + API Key

1. 注册登录：[https://cron-job.org](https://cron-job.org)
2. 打开 Console → **Settings** → 生成 **API Key**
3. 复制保存

---

## 方式 A：一键脚本（推荐）

```powershell
cd "d:\person_project\工具\自动签到脚本\workbuddy"

$env:CRONJOB_ORG_API_KEY = "粘贴_cron-job.org_的_API_Key"
$env:GITHUB_PAT = "粘贴_GitHub_PAT"

python scripts/setup_cronjob_org.py
```

会创建 / 更新四条任务：

| 标题 | 时间（北京） | 作用 |
|------|--------------|------|
| NewAPI Daily Checkin (external) | **08:00** | 主签到 |
| WorkBuddy Daily Checkin (external) | **08:00** | 主签到 |
| NewAPI Watchdog (external) | **09:00** | 补签看门狗 |
| WorkBuddy Watchdog (external) | **09:00** | 补签看门狗 |

完成后去 [console.cron-job.org](https://console.cron-job.org/) 对任务点 **Run now** 试跑。

---

## 方式 B：网页手动建任务

每个任务：**POST**，时区 **Asia/Shanghai**，Body：`{"ref":"main"}`

Headers：

```text
Authorization: Bearer <你的_GitHub_PAT>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
User-Agent: cron-job-org-workbuddy
```

| 标题 | 时间 | URL |
|------|------|-----|
| NewAPI 主签到 | 08:00 | `.../actions/workflows/chshapi-checkin.yml/dispatches` |
| WorkBuddy 主签到 | 08:00 | `.../actions/workflows/checkin.yml/dispatches` |
| NewAPI 看门狗 | 09:00 | 同上 chshapi-checkin.yml |
| WorkBuddy 看门狗 | 09:00 | 同上 checkin.yml |

完整 URL 前缀：

```text
https://api.github.com/repos/xiaoyewocaishizuidiaode/workbuddy-checkin
```

成功时 GitHub 通常返回 **204**。

---

## 和仓库里 schedule 的关系

工作流里 GitHub `schedule` 也改成 **08:00 / 09:00** 作备份。外部准时触发后若又晚到，脚本会把「今日已签到」当成成功。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| cron-job.org 返回 401 | GitHub PAT 错了或过期 |
| 看不到 Actions 权限 | 在 **Repository permissions** 里找，不要加 Account permissions |
| PAT 泄露 | 立刻在 GitHub 撤销，并在 cron-job.org 改 Header |
