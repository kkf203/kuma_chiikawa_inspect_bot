# Before running, install required packages:
# pip3 install requests beautifulsoup4 python-telegram-bot

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# 檢查網址是否有效的函數
def check_url(url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            page_text = soup.get_text().lower()
            if "the page you’re looking for couldn’t be found" not in page_text:
                return True, "有效"
            else:
                return False, "無效 (包含錯誤訊息)"
        else:
            return False, f"無效 (狀態碼: {response.status_code})"
    except requests.RequestException as e:
        return False, f"無效 (錯誤: {str(e)})"

# 處理 /start 命令
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "歡迎使用增強版 URL 測試機器人！\n"
        "機器人僅回報有效網址。\n"
        "可用命令：\n"
        "/seturl <網址> - 設置基礎網址（需包含 {}）\n"
        "/setattempts <次數> - 設置測試次數\n"
        "/test - 開始測試\n"
        "/pause - 暫停測試\n"
        "/resume - 恢復測試\n"
        "/stop - 終止測試並顯示結果\n"
        "預設：網址 = https://nagano-market.jp/cdn/shop/files/{}_1.jpg，次數 = 200"
    )

# 處理 /seturl 命令
async def set_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        new_url = " ".join(context.args)
        if "{}" in new_url:
            context.user_data["base_url"] = new_url
            await update.message.reply_text(f"基礎網址已設置為：{new_url}")
        else:
            await update.message.reply_text("錯誤：網址必須包含 {} 作為 ID 占位符，例如 https://example.com/{}_1.jpg")
    else:
        await update.message.reply_text("請提供網址，例如：/seturl https://example.com/{}_1.jpg")

# 處理 /setattempts 命令
async def set_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        try:
            attempts = int(context.args[0])
            if attempts > 0:
                context.user_data["max_attempts"] = attempts
                await update.message.reply_text(f"測試次數已設置為：{attempts}")
            else:
                await update.message.reply_text("錯誤：測試次數必須為正整數")
        except ValueError:
            await update.message.reply_text("錯誤：請輸入有效的數字，例如 /setattempts 100")
    else:
        await update.message.reply_text("請提供測試次數，例如：/setattempts 100")

# 處理 /test 命令
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 檢查是否已在測試
    if context.user_data.get("testing", False):
        await update.message.reply_text("測試已在進行中！請先使用 /pause 暫停或 /stop 終止。")
        return

    # 設置初始參數
    base_url = context.user_data.get("base_url", "https://nagano-market.jp/cdn/shop/files/{}_1.jpg")
    max_attempts = context.user_data.get("max_attempts", 200)
    initial_number = 4571609355779  # 從第一個有效 ID 開始
    context.user_data.update({
        "testing": True,
        "current_number": initial_number,
        "attempts": 0,
        "max_attempts": max_attempts,
        "valid_urls": [],
        "consecutive_invalid": 0,
        "paused": False
    })

    await update.message.reply_text(f"開始測試網址（基礎網址：{base_url}，次數：{max_attempts}）...")

    # 測試循環
    while context.user_data["attempts"] < context.user_data["max_attempts"] and context.user_data["testing"]:
        if context.user_data.get("paused", False):
            break  # 如果暫停，退出循環

        current_number = context.user_data["current_number"]
        test_url = base_url.format(current_number)
        is_valid, status = check_url(test_url)

        # 僅當有效時發送訊息
        if is_valid:
            message = (
                f"嘗試 {context.user_data['attempts'] + 1}: 數字 = {current_number}\n"
                f"網址 = {test_url}\n"
                f"結果: {status}"
            )
            await update.message.reply_text(message)
            context.user_data["valid_urls"].append(test_url)
            context.user_data["consecutive_invalid"] = 0
            context.user_data["current_number"] += 7
        else:
            context.user_data["consecutive_invalid"] += 1
            if context.user_data["consecutive_invalid"] >= 5:
                context.user_data["current_number"] += 17
                context.user_data["consecutive_invalid"] = 0
            else:
                context.user_data["current_number"] += 7

        context.user_data["attempts"] += 1

    # 如果測試完成（非暫停）
    if context.user_data["attempts"] >= context.user_data["max_attempts"] and context.user_data["testing"]:
        await send_summary(update, context)
        context.user_data.clear()

# 處理 /pause 命令
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("testing", False):
        context.user_data["paused"] = True
        await update.message.reply_text("測試已暫停。使用 /resume 繼續或 /stop 終止。")
    else:
        await update.message.reply_text("目前沒有進行中的測試。")

# 處理 /resume 命令
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("paused", False):
        context.user_data["paused"] = False
        base_url = context.user_data.get("base_url", "https://nagano-market.jp/cdn/shop/files/{}_1.jpg")
        await update.message.reply_text("恢復測試...")
        
        # 繼續測試循環
        while context.user_data["attempts"] < context.user_data["max_attempts"] and context.user_data["testing"]:
            if context.user_data.get("paused", False):
                break

            current_number = context.user_data["current_number"]
            test_url = base_url.format(current_number)
            is_valid, status = check_url(test_url)

            # 僅當有效時發送訊息
            if is_valid:
                message = (
                    f"嘗試 {context.user_data['attempts'] + 1}: 數字 = {current_number}\n"
                    f"網址 = {test_url}\n"
                    f"結果: {status}"
                )
                await update.message.reply_text(message)
                context.user_data["valid_urls"].append(test_url)
                context.user_data["consecutive_invalid"] = 0
                context.user_data["current_number"] += 7
            else:
                context.user_data["consecutive_invalid"] += 1
                if context.user_data["consecutive_invalid"] >= 5:
                    context.user_data["current_number"] += 17
                    context.user_data["consecutive_invalid"] = 0
                else:
                    context.user_data["current_number"] += 7

            context.user_data["attempts"] += 1

        if context.user_data["attempts"] >= context.user_data["max_attempts"] and context.user_data["testing"]:
            await send_summary(update, context)
            context.user_data.clear()
    else:
        await update.message.reply_text("沒有暫停的測試。請使用 /test 開始新測試。")

# 處理 /stop 命令
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("testing", False):
        context.user_data["testing"] = False
        await send_summary(update, context)
        context.user_data.clear()
        await update.message.reply_text("測試已終止。")
    else:
        await update.message.reply_text("目前沒有進行中的測試。")

# 發送總結的輔助函數
async def send_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    valid_urls = context.user_data.get("valid_urls", [])
    summary = "=== 測試完成 ===\n"
    if valid_urls:
        summary += f"共找到 {len(valid_urls)} 個有效網址：\n"
        # 分段發送以避免訊息過長
        for i in range(0, len(valid_urls), 50):  # 每 50 個網址分一段
            chunk = valid_urls[i:i+50]
            chunk_summary = "".join(f"{i+j+1}. {url}\n" for j, url in enumerate(chunk))
            await update.message.reply_text(summary + chunk_summary)
            summary = ""
    else:
        summary += "未找到任何有效網址。"
        await update.message.reply_text(summary)

def main():
    # 替換為您的 BotFather 提供的 API 令牌
    API_TOKEN = "7928836301:AAGBenKQmlgH9dyLNHkgbhVRq8INdjGiPg8"
    
    # 初始化應用程式
    application = Application.builder().token(API_TOKEN).build()
    
    # 添加命令處理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("seturl", set_url))
    application.add_handler(CommandHandler("setattempts", set_attempts))
    application.add_handler(CommandHandler("test", test))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("stop", stop))
    
    # 開始輪詢
    application.run_polling()

if __name__ == "__main__":
    main()
