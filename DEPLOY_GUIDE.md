# 🎓 广金万事屋师兄 - 部署指南

## 快速部署到 Streamlit Cloud（推荐）

### 步骤 1：创建 GitHub 仓库

1. 打开 [GitHub](https://github.com)，登录你的账号
2. 点击右上角 "New" 创建新仓库
3. 仓库名建议：`gduf-super-senior-agent`
4. 设置为公开仓库（Public），不要初始化 README

### 步骤 2：上传代码到 GitHub

```bash
# 初始化 Git（如果还没初始化）
cd 721
git init
git add .
git commit -m "Initial commit"

# 添加远程仓库（替换为你的仓库地址）
git remote add origin https://github.com/你的用户名/gduf-super-senior-agent.git
git branch -M main
git push -u origin main
```

### 步骤 3：部署到 Streamlit Cloud

1. 打开 [Streamlit Community Cloud](https://share.streamlit.io)
2. 登录你的 GitHub 账号
3. 点击 "New app"
4. 选择你的仓库、分支（main）、主文件路径（`app.py`）
5. 点击 "Deploy!"

### 步骤 4：配置 API Key（重要！）

部署成功后，在应用页面右上角点击 "Manage app" → "Settings" → "Secrets"

在 Secrets 中添加以下内容：

```toml
DEEPSEEK_API_KEY = "你的DeepSeek API Key"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
```

点击 "Save"，然后重启应用。

### 步骤 5：分享给朋友

部署成功后，你会获得一个类似 `https://your-app-name.streamlit.app` 的链接。

**在手机上使用：**

1. 用手机浏览器打开链接
2. **iOS Safari**：点击底部分享按钮 → "添加到主屏幕"
3. **Android Chrome**：点击三点菜单 → "添加到主屏幕"

这样应用就会像原生 App 一样出现在手机桌面上！

---

## 部署到其他平台

### 部署到 Heroku

```bash
# 安装 Heroku CLI
# 创建应用
heroku create gduf-super-senior-agent

# 设置环境变量
heroku config:set DEEPSEEK_API_KEY=你的DeepSeek API Key
heroku config:set DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# 部署
git push heroku main
```

### 部署到 Vercel

1. 安装 Vercel CLI：`npm install -g vercel`
2. 创建 `vercel.json`：

```json
{
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app.py"
    }
  ]
}
```

3. 部署：`vercel --prod`

---

## 移动端适配说明

### PWA 特性

应用已配置 PWA 支持，用户可以：
- ✅ 将应用添加到手机主屏幕
- ✅ 全屏运行（无浏览器地址栏）
- ✅ 离线缓存（基础功能）
- ✅ 自定义图标和启动画面

### 响应式设计

应用使用 Streamlit 的 `centered` 布局，自动适配不同屏幕尺寸。

---

## 故障排除

### 常见问题

1. **API Key 无效**
   - 检查 Secrets 配置是否正确
   - 确保没有多余的空格或引号

2. **部署失败**
   - 检查 `requirements.txt` 是否完整
   - 检查 GitHub 仓库是否包含所有必要文件

3. **应用加载慢**
   - 首次加载需要下载 HuggingFace 模型
   - 建议在 Streamlit Cloud 设置中增加资源配额

4. **手机上无法添加到主屏幕**
   - 确保使用 HTTPS 访问
   - iOS 用户需要使用 Safari 浏览器
   - Android 用户需要使用 Chrome 浏览器

---

## 技术栈

| 组件 | 说明 |
|------|------|
| **前端框架** | Streamlit 1.32.0 |
| **后端逻辑** | LangChain 0.1.20 |
| **大模型** | DeepSeek API (deepseek-chat) |
| **向量数据库** | FAISS |
| **嵌入模型** | HuggingFace all-MiniLM-L6-v2 |
| **部署平台** | Streamlit Community Cloud |
