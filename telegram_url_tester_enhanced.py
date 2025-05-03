import os
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Get Bot Token from environment variable
API_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Function to check if a URL is valid
def check_url(url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.find('title')
            if title and "Page not found" not in title.text:
                return True
        return False
    except requests.RequestException:
        return False

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "歡迎使用增強版 URL 測試機器人！\n"
        "命令：\n"
        "/seturl <網址> - 設置網址模板\n"
        "/setattempts <次數> - 設置測試次數\n"
        "/setid <數字> - 設置初始數字\n"
        "/test - 開始測試\n"
        "/pause - 暫停測試\n"
        "/resume - 繼續測試\n"
        "/stop - 停止測試"
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
    initial_number = context.user_data.get('initial_number', 4571609355779)  # Default if not set

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
        
        await asyncio.sleep(0.5)  # Prevent overwhelming the server

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

# Main function
async def main():
    application = Application.builder().token(API_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("seturl", set_url))
    application.add_handler(CommandHandler("setattempts", set_attempts))
    application.add_handler(CommandHandler("setid", set_id))
    application.add_handler(CommandHandler("test", test))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("stop", stop))

    await application.run_polling(timeout=10, poll_interval=1.0)

if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())