import asyncio
import logging
import os
import threading
import httpx
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError

# 設置日誌
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 初始化 Flask 應用
flask_app = Flask(__name__)

@flask_app.route('/health')
def health():
    """健康檢查端點，供 Render 使用"""
    return "OK", 200

async def check_url(url: str) -> bool:
    """檢查指定 URL 是否有效。"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            invalid_messages = [
                "The page you’re looking for couldn’t be found.",
                "Not Found",
                "404error"
            ]
            is_invalid = any(msg in response.text for msg in invalid_messages)
            return not is_invalid
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error for {url}: {e}")
        return False
    except httpx.RequestError as e:
        logger.error(f"Request error for {url}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error for {url}: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /start 命令，提供 BOT 說明。"""
    example_url = "https://example.com/cdn/shop/files/{}_1.jpg"
    example_attempts = 10
    example_id = 123456

    context.user_data['url_template'] = example_url
    context.user_data['attempts'] = example_attempts
    context.user_data['start_id'] = example_id
    context.user_data['testing'] = False

    message = (
        "歡迎使用 URL 測試 BOT！\n\n"
        "請按照以下步驟操作：\n"
        f"1. 設置 URL 模板，例如：/seturl {example_url}\n"
        f"2. 設置測試次數，例如：/setattempts {example_attempts}\n"
        f"3. 設置起始 ID，例如：/setid {example_id}\n"
        "4. 執行 /test 開始測試\n\n"
        "其他命令：\n"
        "- /stop: 停止當前測試\n"
        "- /reset: 重置所有設置\n"
        "- /showsettings: 顯示當前設置\n\n"
        "開始設置吧！"
    )
    await update.message.reply_text(message)
    logger.info("Received start command")

async def set_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /seturl 命令，設置 URL 模板。"""
    if not context.args:
        await update.message.reply_text("請提供 URL 模板，例如：/seturl https://example.com/cdn/shop/files/{}_1.jpg")
        return
    context.user_data['url_template'] = context.args[0]
    await update.message.reply_text(f"URL 模板已設為：{context.user_data['url_template']}")
    logger.info("Received seturl command")

async def set_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /setattempts 命令，設置測試次數。"""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("請提供有效的測試次數，例如：/setattempts 10")
        return
    context.user_data['attempts'] = int(context.args[0])
    await update.message.reply_text(f"測試次數已設為：{context.user_data['attempts']}")
    logger.info("Received setattempts command")

async def set_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /setid 命令，設置起始 ID。"""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("請提供有效的起始 ID，例如：/setid 123456")
        return
    context.user_data['start_id'] = int(context.args[0])
    await update.message.reply_text(f"起始 ID 已設為：{context.user_data['start_id']}")
    logger.info("Received setid command")

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /showsettings 命令，顯示當前設置。"""
    url_template = context.user_data.get('url_template', '未設置')
    attempts = context.user_data.get('attempts', '未設置')
    start_id = context.user_data.get('start_id', '未設置')
    message = (
        f"當前設置：\n"
        f"URL 模板：{url_template}\n"
        f"測試次數：{attempts}\n"
        f"起始 ID：{start_id}"
    )
    await update.message.reply_text(message)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /reset 命令，重置所有設置。"""
    context.user_data.clear()
    context.user_data['testing'] = False
    await update.message.reply_text("所有設置已重置！請重新設置 URL、測試次數和起始 ID。")
    logger.info("Received reset command")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /stop 命令，停止當前測試。"""
    if context.user_data.get('testing', False):
        context.user_data['testing'] = False
        await update.message.reply_text("測試已停止！")
        logger.info("Received stop command")
    else:
        await update.message.reply_text("目前沒有正在進行的測試。")

async def run_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """執行 URL 測試邏輯。"""
    if context.user_data.get('testing', False):
        await update.message.reply_text("測試已在進行！請先 /stop 或等待測試完成。")
        return

    if 'url_template' not in context.user_data or 'attempts' not in context.user_data or 'start_id' not in context.user_data:
        await update.message.reply_text("請先設置 URL 模板、測試次數和起始 ID！使用 /seturl, /setattempts, /setid。")
        return

    context.user_data['testing'] = True
    url_template = context.user_data['url_template']
    attempts = context.user_data['attempts']
    start_id = context.user_data['start_id']
    valid_urls = []

    try:
        await update.message.reply_text("測試開始！請稍候...")
        logger.info("Received test command")

        for i in range(attempts):
            if not context.user_data.get('testing', False):
                await update.message.reply_text("測試被中止。")
                break

            current_id = start_id + i
            url = url_template.format(current_id)
            logger.info(f"Testing URL {url}")

            is_valid = await check_url(url)
            if is_valid:
                valid_urls.append(url)

            if (i + 1) % 25 == 0:
                await update.message.reply_text(f"已測試 {i + 1}/{attempts} 個 URL，有效 URL 數量：{len(valid_urls)}")

            await asyncio.sleep(1)

        if valid_urls:
            message = "測試完成！以下是所有有效網址：\n" + "\n".join(valid_urls)
        else:
            message = "測試完成，沒有找到有效網址。"
        await update.message.reply_text(message)
        logger.info("Test completed")

    except TelegramError as e:
        logger.error(f"Telegram error during test: {e}")
        await update.message.reply_text("發送訊息時發生錯誤，請稍後再試。")
    except Exception as e:
        logger.error(f"Unexpected error during test: {e}")
        await update.message.reply_text("測試過程中發生未知錯誤，請稍後再試。")
    finally:
        context.user_data['testing'] = False
        logger.info("Test state reset")

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /test 命令，啟動測試。"""
    await run_test(update, context)

def run_flask():
    """在獨立線程中運行 Flask 伺服器"""
    port = int(os.getenv("PORT", 10000))  # 使用 Render 的 PORT，默認為 10000
    flask_app.run(host="0.0.0.0", port=port, debug=False)

async def run_bot():
    """運行 Telegram BOT"""
    token = "7928836301:AAHlTTCy0QFJ9lNz3kRMgR66-BfXfDA6ErM"
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("seturl", set_url))
    application.add_handler(CommandHandler("setattempts", set_attempts))
    application.add_handler(CommandHandler("setid", set_id))
    application.add_handler(CommandHandler("test", test))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("showsettings", show_settings))

    try:
        await application.run_polling(timeout=10, poll_interval=1.0, drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Polling error: {e}")
        logger.info("Restarting polling after 5 seconds...")
        await asyncio.sleep(5)
        await run_bot()  # 遞迴重試

def main():
    """主函數，啟動 Flask 和 Telegram BOT"""
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    asyncio.run(run_bot())  # 使用 asyncio.run 簡化事件循環管理

if __name__ == '__main__':
    main()
