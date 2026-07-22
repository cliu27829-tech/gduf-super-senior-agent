import os
import sys
import subprocess

def check_git():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except:
        return False

def setup_git():
    print("📦 配置 Git...")
    try:
        subprocess.run(["git", "config", "--global", "user.name", "GDUF Agent"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "agent@gduf.edu.cn"], check=True)
        print("✅ Git 配置完成")
    except Exception as e:
        print(f"❌ Git 配置失败: {e}")
        return False
    return True

def initialize_repo():
    print("📁 初始化 Git 仓库...")
    try:
        if os.path.exists(".git"):
            print("ℹ️ 仓库已存在，跳过初始化")
            return True
        
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "广金万事屋师兄 - 初始化"], check=True)
        print("✅ 仓库初始化完成")
        return True
    except Exception as e:
        print(f"❌ 仓库初始化失败: {e}")
        return False

def show_deploy_instructions():
    print("\n" + "="*60)
    print("🎓 广金万事屋师兄 - 部署指南")
    print("="*60)
    print("""

📋 部署步骤：

1. 创建 GitHub 仓库
   → 打开 https://github.com/new
   → 仓库名：gduf-super-senior-agent
   → 选择 Public（公开）
   → 点击 Create repository

2. 关联远程仓库（在命令行执行）：
   git remote add origin https://github.com/你的用户名/gduf-super-senior-agent.git
   git branch -M main
   git push -u origin main

3. 部署到 Streamlit Cloud
   → 打开 https://share.streamlit.io
   → 使用 GitHub 账号登录
   → 点击 New app
   → 选择仓库：你的用户名/gduf-super-senior-agent
   → 分支：main
   → 主文件路径：app.py
   → 点击 Deploy!

4. 配置 API Key（重要！）
   → 在应用页面点击 Manage app → Settings → Secrets
   → 输入：
     DEEPSEEK_API_KEY = "你的DeepSeek API Key"
     DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
   → 点击 Save，然后重启应用

5. 分享链接
   → 部署成功后获得链接：https://xxx.streamlit.app
   → 发送给朋友即可使用！

📱 手机使用：
   iOS Safari：点击分享 → 添加到主屏幕
   Android Chrome：三点菜单 → 添加到主屏幕

""")
    print("="*60)

def main():
    print("🎓 广金万事屋师兄 - 部署工具")
    print("="*60)
    
    if not check_git():
        print("❌ Git 未安装，请先安装 Git：")
        print("   → 下载地址：https://git-scm.com/download/win")
        print("   → 安装后重新运行此脚本")
        return
    
    print("✅ Git 已安装")
    
    if not setup_git():
        return
    
    if not initialize_repo():
        return
    
    show_deploy_instructions()
    
    print("\n🔗 本地访问地址：http://localhost:8501")
    print("📝 部署完成后，请将你的 GitHub 用户名告诉我，我帮你验证！")

if __name__ == "__main__":
    main()