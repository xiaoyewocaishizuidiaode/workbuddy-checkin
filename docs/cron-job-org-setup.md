# 用 cron-job.org 准时触发 GitHub Actions 签到

GitHub 自带的 `schedule` 经常晚几小时。做法是：

```text
cron-job.org（准时闹钟）
      ↓ POST workflow_dispatch
GitHub Actions（仍然跑原来的签到脚本）
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
| Permissions → Actions | **Read and write** |
| Permissions → Contents | Read-only（建议） |
| Permissions → Metadata | Read-only |

Classic token 则勾选 `repo` + `workflow`。

### 2）cron-job.org 账号 + API Key

1. 注册登录：[https://cron-job.org](https://cron-job.org)
2. 打开 Console → **Settings** → 生成 **API Key**
3. 复制保存

---

## 方式 A：一键脚本（推荐）

在仓库根目录执行（PowerShell）：

```powershell
cd "d:\person_project\工具\自动签到脚本\workbuddy"

$env:CRONJOB_ORG_API_KEY = "粘贴_cron-job.org_的_API_Key"
$env:GITHUB_PAT = "粘贴_GitHub_PAT"

python scripts/setup_cronjob_org.py
```

会创建 / 更新两条任务：

| 标题 | 时间（北京） | 触发的工作流 |
|------|--------------|--------------|
| NewAPI Daily Checkin (external) | 每天 **08:00** | `chshapi-checkin.yml` |
| WorkBuddy Daily Checkin (external) | 每天 **09:05** | `checkin.yml` |

完成后去 [console.cron-job.org](https://console.cron-job.org/) 对任务点 **Run now**，再到 GitHub **Actions** 看是否出现 `workflow_dispatch` 且为绿色。

---

## 方式 B：网页手动建任务

对每个工作流 **Create cronjob** 一次。

### 公共设置

- Request method: **POST**
- Timezone: **Asia/Shanghai**
- Body:

```json
{"ref":"main"}
```

Headers：

```text
Authorization: Bearer <你的_GitHub_PAT>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
User-Agent: cron-job-org-workbuddy
```

### 任务 1 — NewAPI（含 hcnsec）

- Title: `NewAPI Daily Checkin (external)`
- URL:

```text
https://api.github.com/repos/xiaoyewocaishizuidiaode/workbuddy-checkin/actions/workflows/chshapi-checkin.yml/dispatches
```

- Schedule: 每天 **08:00**

### 任务 2 — WorkBuddy

- Title: `WorkBuddy Daily Checkin (external)`
- URL:

```text
https://api.github.com/repos/xiaoyewocaishizuidiaode/workbuddy-checkin/actions/workflows/checkin.yml/dispatches
```

- Schedule: 每天 **09:05**

成功时 GitHub 通常返回 **204**，cron-job.org 记为成功即可。

---

## 和仓库里 schedule 的关系

工作流里仍保留 GitHub `schedule` 作为备份。外部准时触发后，若 GitHub 自己的定时又晚到，脚本会把「今日已签到」当成成功，一般无副作用。

若只想用外部闹钟，可删掉 YAML 里的 `schedule:` 段，只留 `workflow_dispatch`。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| cron-job.org 返回 401 | GitHub PAT 错了或过期，换新 token |
| 401 + Actions 权限 | Fine-grained 需勾选目标仓库的 Actions: Write |
| 任务没跑 | 看 console 时区是否 Asia/Shanghai，任务是否 Enabled |
| PAT 泄露 | 立刻在 GitHub 撤销，并在 cron-job.org 改 Header |
