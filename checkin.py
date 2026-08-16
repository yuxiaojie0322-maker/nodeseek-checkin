#!/usr/bin/env python3
"""
NodeSeek 每日签到领鸡腿脚本
=======================
使用 undetected-chromedriver 绕过 Cloudflare，然后在浏览器内调用 API 签到。

用法:
    export NS_COOKIE="session=xxx; pjwt=yyy"
    export TG_BOT_TOKEN="xxx"
    export TG_CHAT_ID="xxx"
    python checkin.py

环境变量:
    NS_COOKIE         - NodeSeek 登录 Cookie（必填，从浏览器 F12 复制）
    TG_BOT_TOKEN      - Telegram Bot Token（可选）
    TG_CHAT_ID        - Telegram 用户/群组 ID（可选）
    HEADLESS          - 无头模式，默认 true（可选）
"""

import os
import re
import sys
import time
import json
import shutil
import subprocess
import traceback

import requests

try:
    import undetected_chromedriver as uc
except ImportError:
    print("请先安装 undetected_chromedriver: pip install undetected-chromedriver")
    sys.exit(1)

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("请先安装 selenium: pip install selenium")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ========== 配置 ==========
NS_COOKIE = os.environ.get("NS_COOKIE", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
HEADLESS = os.environ.get("HEADLESS", "true").lower() in ("true", "1", "yes")

CHECKIN_URL = "https://www.nodeseek.com/api/attendance?random=true"
SITE_URL = "https://www.nodeseek.com/board"

CF_CHALLENGE_MARKERS = (
    "just a moment", "checking your browser",
    "verify you are human", "enable javascript and cookies",
    "challenges.cloudflare.com",
)


# ========== 工具函数 ==========
def detect_chrome_version():
    """检测 Chrome 大版本号。"""
    for binary in ("google-chrome", "chromium-browser", "chromium", "chrome"):
        exe = shutil.which(binary)
        if not exe:
            continue
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15).stdout
            m = re.search(r'(\d+)\.\d+\.\d+', out)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    return None


def parse_cookies(raw):
    """解析 NS_COOKIE 字符串。"""
    pairs = []
    if not raw:
        return pairs
    name_pat = re.compile(r'^[A-Za-z0-9!#$%&\'*+\-.^_`|~]+$')
    for chunk in re.split(r'[;\r\n]+', raw):
        segment = chunk.strip()
        if not segment:
            continue
        name, sep, value = segment.partition('=')
        if sep and name_pat.match(name.strip()):
            # 跳过 cf_clearance，让浏览器重新获取
            if name.strip().lower() == "cf_clearance":
                continue
            pairs.append((name.strip(), value.strip()))
    return pairs


def is_cf_challenge(driver):
    """判断是否在 Cloudflare 挑战页。"""
    try:
        title = (driver.title or "").lower()
        # 只检查标题，不检查 page_source（避免误判）
        if any(m in title for m in CF_CHALLENGE_MARKERS):
            return True
        # 检查 URL 是否包含 cloudflare 挑战域名
        url = (driver.current_url or "").lower()
        if "challenges.cloudflare.com" in url:
            return True
        return False
    except Exception:
        return False


def wait_cf(driver, timeout=30):
    """等待 Cloudflare 挑战通过（undetected-chromedriver 通常自动通过）。"""
    deadline = time.time() + timeout
    reloaded = False
    while time.time() < deadline:
        if not is_cf_challenge(driver):
            return True
        elapsed = int(time.time() - (deadline - timeout))
        print(f"  ⏳ 等待 Cloudflare 通过... ({elapsed}s)", end="\r")
        time.sleep(2)
        if not reloaded and elapsed > 12:
            print("\n  🔄 刷新页面...")
            try:
                driver.refresh()
                time.sleep(2)
            except Exception:
                pass
            reloaded = True
    print()
    print("❌ Cloudflare 挑战超时")
    return False


def create_driver():
    """创建 undetected-chromedriver 实例。"""
    print("🚀 启动浏览器...")
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1365,900')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36')

    if HEADLESS:
        print("  无头模式")
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
    else:
        print("  有头模式")

    version_main = detect_chrome_version()
    if version_main:
        print(f"  Chrome 版本: {version_main}")
        driver = uc.Chrome(options=options, version_main=version_main)
    else:
        driver = uc.Chrome(options=options)

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.set_window_size(1365, 900)
    print("✅ 浏览器启动成功")
    return driver


def send_tg(title, content):
    """发送 Telegram 通知。"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("📢 TG 未配置，跳过推送")
        return False
    try:
        text = f"<b>{title}</b>\n\n{content}"
        if len(text) > 4000:
            text = text[:3997] + "..."
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if resp.json().get("ok"):
            print("✅ Telegram 推送成功")
            return True
        else:
            print(f"❌ Telegram 推送失败: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram 推送异常: {e}")
        return False


# ========== 核心签到 ==========
def run():
    print("=" * 50)
    print("🍗 NodeSeek 每日签到领鸡腿")
    print("=" * 50)

    if not NS_COOKIE:
        print("❌ 未设置 NS_COOKIE 环境变量")
        print("   请先设置: export NS_COOKIE='session=xxx; pjwt=yyy'")
        return 1

    cookies = parse_cookies(NS_COOKIE)
    print(f"📝 解析到 {len(cookies)} 个 Cookie")

    driver = None
    try:
        driver = create_driver()

        # 1. 访问首页，过 Cloudflare
        print(f"\n🌐 访问 {SITE_URL} ...")
        driver.get(SITE_URL)
        time.sleep(3)  # 给 undetected-chromedriver 时间处理 Cloudflare
        if not wait_cf(driver):
            send_tg("🍗 NodeSeek 签到", "签到失败: Cloudflare 挑战未通过")
            return 1

        # 2. 注入 Cookie
        print("\n📝 注入 Cookie...")
        for name, value in cookies:
            try:
                driver.add_cookie({'name': name, 'value': value, 'domain': '.nodeseek.com', 'path': '/'})
            except Exception as e:
                print(f"  ⚠️ 注入 {name} 失败: {e}")

        # 3. 刷新使 Cookie 生效
        print("🔄 刷新页面...")
        driver.refresh()
        time.sleep(3)  # 等待 Cookie 生效
        if not wait_cf(driver):
            send_tg("🍗 NodeSeek 签到", "签到失败: 刷新后 Cloudflare 未通过")
            return 1

        # 4. 在浏览器内调用签到 API（自动携带 Cloudflare 会话 + Cookie）
        print(f"\n📤 调用签到 API: {CHECKIN_URL}")
        result = driver.execute_script("""
            return fetch(arguments[0], {
                method: 'POST',
                credentials: 'include',
                headers: {'Accept': 'application/json, text/plain, */*'}
            }).then(res => {
                return res.text().then(body => ({
                    status: res.status,
                    body: body
                }));
            });
        """, CHECKIN_URL)

        status = result.get("status", 0)
        body = result.get("body", "")

        print(f"  HTTP {status}")
        print(f"  响应: {body[:200]}")

        # 解析结果
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        success = False
        detail = ""
        gain = ""
        current = ""

        try:
            data = json.loads(body)
            if data.get("success"):
                success = True
                gain = str(data.get("gain", "?"))
                current = str(data.get("current", "?"))
                detail = f"签到成功 +{gain} 鸡腿 (总计 {current})"
                print(f"\n✅ {detail}")
            elif "已完成签到" in data.get("message", "") or "请勿重复" in data.get("message", ""):
                success = True  # 已签到也算成功
                msg = data.get("message", "今天已完成签到")
                detail = msg
                print(f"\nℹ️ {detail}")
            else:
                msg = data.get("message", body)
                detail = f"签到失败: {msg}"
                print(f"\n❌ {detail}")
        except json.JSONDecodeError:
            if status == 200:
                detail = f"响应解析失败: {body[:100]}"
                print(f"\n❌ {detail}")
            else:
                detail = f"HTTP {status}: {body[:100]}"
                print(f"\n❌ {detail}")

        # 5. 构建通知内容
        lines = [f"🕐 {now}"]

        if success:
            lines.append(f"✅ 签到成功")
            if gain:
                lines.append(f"🍗 今日获得 +{gain} 鸡腿")
            if current:
                lines.append(f"💰 账户总计 {current} 鸡腿")
            if detail and not gain and not current:
                lines.append(f"📌 {detail}")
        else:
            lines.append(f"❌ 签到失败")
            lines.append(f"📌 {detail}")

        # 尝试获取账号信息（等级 + 鸡腿总数）
        try:
            driver.get("https://www.nodeseek.com/")
            time.sleep(3)
            page_text = (driver.find_element(By.TAG_NAME, "body").text or "")
            level_m = re.search(r'等级\s*Lv\.?\s*(\d+)', page_text, re.I)
            if level_m:
                lines.append(f"🏅 Lv.{level_m.group(1)}")
            # 如果 API 没返回 current，从页面抓鸡腿数
            if not current:
                leg_m = re.search(r'鸡腿\s*(\d+(?:\.\d+)?)', page_text)
                if leg_m:
                    lines.append(f"💰 账户总计 {leg_m.group(1)} 鸡腿")
        except Exception:
            pass

        content = "\n".join(lines)
        print("\n" + "=" * 50)
        print(content)
        print("=" * 50)

        # 6. 推送 Telegram
        title = "🍗 NodeSeek 签到" + ("" if success else " ❌")
        send_tg(title, content)

        return 0 if success else 1

    except Exception as e:
        print(f"\n❌ 脚本异常: {e}")
        traceback.print_exc()
        send_tg("🍗 NodeSeek 签到（异常）", f"脚本执行异常: {type(e).__name__} {str(e)}")
        return 1

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(run())