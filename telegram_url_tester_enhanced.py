import os
import requests
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask
import threading
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import pytz

# Initialize Flask app
app = Flask(__name__)

# Basic route to satisfy Render's port requirement
@app.route('/')
def home():
    return "Telegram Bot is running!"

# Get Bot Token from environment variable
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

# Initialize scheduler for timed tests
scheduler = AsyncIOScheduler()
scheduler.start()

# Function to check if a URL is valid
def check_url(url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            if "The page you’re looking for couldn’t be found." not in response.text:
                return True
            return False
        return False
    except requests.RequestException:
        return False

# Command to handle standalone "/"
async def slash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/":
        await update.message.reply_text(
            "可用命令：\n"
            "/start - 顯示歡迎訊息\n"
            "/seturl <網址> - 設置網址模板\n"
            "/setattempts <次數> - 設置測試次數\n"
            "/setid <數字> - 設置初始數字\n"
            "/test - 開始測試\n"
            "/pause - 暫停測試\n"
            "/resume - 繼續測試\n"
            "/stop - 停止測試\n"
            "/scheduletest <日期> <時間> <時區> - 設定定時測試 (例如 /scheduletest 2025-05-10 14:30 GMT)\n"
            "/stopschedule - 停止定時測試"
        )

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "歡迎使用增強版 URL 測試機器人！\n"
        "可用命令：\n"
        "/start - 顯示歡迎訊息\n"
        "/seturl <網址> - 設置網址模板\n"
        "/setattempts <次數> - 設置測試次數\n"
        "/setid <數字> - 設置初始數字\n"
        "/test - 開始測試\n"
        "/pause - 暫停測試\n"
        "/resume - 繼續測試\n"
        "/stop - 停止測試\n"
        "/scheduletest <日期> <時間> <時區> - 設定定時測試 (例如 /scheduletest 2025-05-10 14:30 GMT)\n"
        "/stopschedule - 停止定時測試"
    )

# Set URL command
async def set_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("請提供網址！格式：/seturl <網址>")
        return
    url = context.args[0]
    context.user_data['url'] = url
    await update.message.reply_text(f"網址已設置為：{url}")

# Set attempts command
async def set_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("請提供有效數字！格式：/setattempts <次數>")
        return
    attempts = int(context.args[0])
    context.user_data['attempts'] = attempts
    await update.message.reply_text(f"測試次數已設置為：{attempts}")

# Set initial number command
async def set_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("請提供有效數字！格式：/setid <數字>")
        return
    initial_number = int(context.args[0])
    context.user_data['initial_number'] = initial_number
    await update.message.reply_text(f"初始數字已設置為：{initial_number}")

# Test command
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'url' not in context.user_data or 'attempts' not in context.user_data:
        await update.message.reply_text("請先設置網址和測試次數！使用 /seturl 和 /setattempts")
        return
    if context.user_data.get('testing', False):
        await update.message.reply_text("測試已在進行！請先 /stop 或 /pause")
        return

    context.user_data['testing'] = True
    context.user_data['paused'] = False
    context.user_data['valid_urls'] = []
    
    url_template = context.user_data['url']
    attempts = context.user_data['attempts']
    initial_number = context.user_data.get('initial_number', 4571609355779)

    for i in range(attempts):
        if not context.user_data['testing']:
            break
        if context.user_data.get('paused', False):
            while context.user_data.get('paused', False) and context.user_data['testing']:
                await asyncio.sleep(1)
        
        current_number = initial_number + i
        test_url = url_template.format(current_number)
        
        if check_url(test_url):
            context.user_data['valid_urls'].append(test_url)
            await update.message.reply_text(
                f"嘗試 {i+1}: 數字 = {current_number}\n"
                f"網址 = {test_url}\n"
                f"結果: 有效"
            )
        else:
            await update.message.reply_text(
                f"嘗試 {i+1}: 數字 = {current_number}\n"
                f"網址 = {test_url}\n"
                f"結果: 無效"
            )
        
        await asyncio.sleep(0.5)

    if context.user_data['testing']:
        valid_urls = context.user_data['valid_urls']
        if valid_urls:
            await update.message.reply_text(
                "測試完成！以下是所有有效網址：\n" + "\n".join(valid_urls)
            )
        else:
            await update.message.reply_text("測試完成，沒有找到有效網址。")
        context.user_data['testing'] = False

# Pause command
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('testing', False):
        await update.message.reply_text("沒有正在進行的測試！")
        return
    context.user_data['paused'] = True
    await update.message.reply_text("測試已暫停。使用 /resume 繼續或 /stop 終止。")

# Resume command
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('testing', False):
        await update.message.reply_text("沒有正在進行的測試！")
        return
    if not context.user_data.get('paused', False):
        await update.message.reply_text("測試未暫停！")
        return
    context.user_data['paused'] = False
    await update.message.reply_text("測試已繼續。")

# Stop command
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('testing', False):
        await update.message.reply_text("沒有正在進行的測試！")
        return
    context.user_data['testing'] = False
    valid_urls = context.user_data.get('valid_urls', [])
    if valid_urls:
        await update.message.reply_text(
            "測試已停止。以下是找到的有效網址：\n" + "\n".join(valid_urls)
        )
    else:
        await update.message.reply_text("測試已停止，沒有找到有效網址。")

# Schedule test command
async def schedule_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'url' not in context.user_data or 'attempts' not in context.user_data:
        await update.message.reply_text("請先設置網址和測試次數！使用 /seturl 和 /setattempts")
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "請提供日期、時間和時區！格式：/scheduletest <日期> <時間> <時區>\n"
            "例如：/scheduletest 2025-05-10 14:30 GMT"
        )
        return

    date_str, time_str, timezone = context.args[0], context.args[1], context.args[2]
    try:
        # Parse date and time
        datetime_str = f"{date_str} {time_str}"
        scheduled_time = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        # Set timezone
        tz = pytz.timezone(timezone)
        scheduled_time = tz.localize(scheduled_time)
    except (ValueError, pytz.exceptions.UnknownTimeZoneError):
        await update.message.reply_text(
            "無效的日期、時間或時區！請使用格式：/scheduletest YYYY-MM-DD HH:MM TZ\n"
            "例如：/scheduletest 2025-05-10 14:30 GMT"
        )
        return

    # Store schedule data
    context.user_data['scheduled_url'] = context.user_data['url']
    context.user_data['scheduled_attempts'] = context.user_data['attempts']
    context.user_data['scheduled_initial_number'] = context.user_data.get('initial_number', 4571609355779)
    context.user_data['scheduled_chat_id'] = update.effective_chat.id

    # Schedule the test
    scheduler.add_job(
        run_scheduled_test,
        trigger=DateTrigger(run_date=scheduled_time),
        args=[context.user_data, context.bot],
        id='scheduled_test'
    )
    await update.message.reply_text(
        f"定時測試已設定於 {scheduled_time} ({timezone}) 執行。\n"
        "使用 /stopschedule 取消定時測試。"
    )

# Run scheduled test
async def run_scheduled_test(user_data, bot):
    url_template = user_data['scheduled_url']
    attempts = user_data['scheduled_attempts']
    initial_number = user_data['scheduled_initial_number']
    chat_id = user_data['scheduled_chat_id']
    valid_urls = []

    for i in range(attempts):
        current_number = initial_number + i
        test_url = url_template.format(current_number)
        
        if check_url(test_url):
            valid_urls.append(test_url)
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"定時測試 - 嘗試 {i+1}: 數字 = {current_number}\n"
                    f"網址 = {test_url}\n"
                    f"結果: 有效"
                )
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"定時測試 - 嘗試 {i+1}: 數字 = {current_number}\n"
                    f"網址 = {test_url}\n"
                    f"結果: 無效"
                )
            )
        
        await asyncio.sleep(0.5)

    if valid_urls:
        await bot.send_message(
            chat_id=chat_id,
            text="定時測試完成！以下是所有有效網址：\n" + "\n".join(valid_urls)
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text="定時測試完成，沒有找到有效網址。"
        )

# Stop scheduled test
async def stop_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if scheduler.get_job('scheduled_test'):
        scheduler.remove_job('scheduled_test')
        await update.message.reply_text("定時測試已取消。")
    else:
        await update.message.reply_text("沒有正在排程的定時測試。")

# Main function for Telegram bot
def main():
    application = Application.builder().token(API_TOKEN).build()

    application.add_handler(MessageHandler(filters.Regex('^/$'), slash_command))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("seturl", set_url))
    application.add_handler(CommandHandler("setattempts", set_attempts))
    application.add_handler(CommandHandler("setid", set_id))
    application.add_handler(CommandHandler("test", test))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("scheduletest", schedule_test))
    application.add_handler(CommandHandler("stopschedule", stop_schedule))

    application.run_polling(timeout=10, poll_interval=1.0)

# Run Flask and Telegram bot in separate threads
def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))

if __name__ == '__main__':
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    # Run Telegram bot
    main()