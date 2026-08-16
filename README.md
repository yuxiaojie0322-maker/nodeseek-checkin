# 🍗 NodeSeek 每日签到领鸡腿

自动签到 NodeSeek 领取每日鸡腿，通过 Telegram 推送结果。

## 快速部署

### 1. 创建 GitHub 仓库

打开 https://github.com/new → 填仓库名 → 选 **Private** → 创建

### 2. 推送代码

```bash
git remote add origin https://github.com/你的用户名/你的仓库名.git
git add .
git commit -m "初始化：NodeSeek 每日签到"
git push -u origin main
```

### 3. 设置 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret

| Secret | 值 |
|--------|-----|
| `NS_COOKIE` | 你的 NodeSeek Cookie |
| `TG_BOT_TOKEN` | `8867499536:AAF2vlfTao3wvy0x7HdlNhZJgfqi5i_vINk` |
| `TG_CHAT_ID` | `7772205808` |

### 4. 手动触发测试

Actions → NodeSeek 每日签到 → Run workflow

以后每天 UTC 0:00（北京时间 8:00）自动签到。
