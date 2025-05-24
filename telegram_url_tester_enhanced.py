import os
import aiohttp
import asyncio
import logging
import json
import time
from datetime import datetime
import pytz
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import uvicorn
import aiofiles
import psutil

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Bot Token from environment variable
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

# Initialize Telegram Application
application = Application.builder().token(API_TOKEN).build()

# Initialize scheduler for timed tests
scheduler = AsyncIOScheduler()

# File to store test state
STATE_FILE = "test_state.json"

# Function to save test state to file (async)
async def save_test_state(user_data):
    state = {
        'testing': user_data.get('testing', False),
        'paused': user_data.get('paused', False),
        'url': user_data.get('url', ''),
        'attempts': user_data.get('attempts', 0),
        'initial_number': user_data.get('initial_number', 4571609355900),
        'current_index': user_data.get('current_index', 0),
        'valid_urls': user_data.get('valid_urls', []),
        'batch_size': user_data.get('batch_size', 300),
        'batch_number': user_data.get('batch_number', 0)
    }
    try:
        async with aiofiles.open(STATE_FILE, 'w') as f:
            await f.write(json.dumps(state))
    except Exception as e:
        logger.error(f"Error saving test state: {e}")

# Function to load test state from file (async)
async def load_test_state(user_data):
    try:
        async with aiofiles.open(STATE_FILE, 'r') as f:
            content = await f.read()
            state = json.loads(content)
        user_data.update(state)
    except FileNotFoundError:
        logger.info("No previous test state found")
    except Exception as e:
        logger.error(f"Error loading test state: {e}")

# Function to log resource usage
def log_resource_usage():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    cpu_percent = psutil.cpu_percent(interval=1)
    logger.info(f"Resource usage: RSS={mem_info.rss / 1024 / 1024:.2f} MB, VMS={mem_info.vms / 1024 / 1024:.2f} MB, CPU={cpu_percent:.2f}%")

# Function to check if a URL is valid with retry
async def check_url(url, retries=3, timeout=5, check_image=False):
    async with aiohttp.ClientSession() as session:
        for attempt in range(retries):
            try:
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '').lower()
                        if check_image:
                            is_valid = 'image/jpeg' in content_type
                            logger.info(f"URL {url} {'is' if is_valid else 'is not'} a JPEG image")
                            return is_valid
                        if 'image' in content_type:
                            logger.info(f"URL {url} is a valid image")
                            return True
                        text = await response.text()
                        if any(phrase in text for phrase in [
                            "The page you’re looking for couldn’t be found.",
                            "Not Found",
                            "404error"
                        ]):
                            logger.info(f"URL {url} invalid due to error message in content")
                            return False
                        return True
                    logger.info(f"URL {url} invalid, status code: {response.status}")
                    return False
            except Exception as e:
                logger.error(f"Attempt {attempt+1} failed for URL {url}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(0.3)
                continue
        logger.error(f"URL {url} failed after {retries} attempts")
        return False

# Command to handle standalone "/"
async def slash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received slash command")
    if update.message.text == "/":
        await update.message.reply_text(
            "歡迎使用增強版 URL 測試機器人！\n"
            "\n"
            "可用命令：\n"
            "\n"
            "基本功能：\n"
            "/start - 顯示歡迎訊息\n"
            "/seturl <網址> - 設置網址模板，例如 /seturl https://chiikawamarket.jp/cdn/shop/files/{}_1.jpg\n"
            "/setattempts <次數> - 設置測試次數，例如 /setattempts 10\n"
            "/setid <數字> - 設置初始數字，例如 /setid 4571609355900\n"
            "/test - 開始測試\n"
            "/pause - 暫停測試\n"
            "/resume - 繼續測試\n"
            "/stop - 停止測試\n"
            "/scheduletest <日期> <時間> <時區> - 設定定時測試，例如 /scheduletest 2025-05-10 14:30 GMT\n"
            "/stopschedule - 停止定時測試\n"
            "\n"
            "---\n"
            "\n"
            "圖片檢查功能：\n"
            "/setimagelinks <網址1>,<網址2>,... - 設置多個圖片網址，例如 /setimagelinks https://example.com/1.jpg,https://example.com/2.jpg\n"
            "/checkimages - 檢查圖片網址是否為 JPEG\n"
            "/scheduleimagecheck - 每小時檢查圖片網址\n"
            "/stopimagecheck - 停止每小時檢查\n"
        )

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received start command")
    await load_test_state(context.user_data)
    if context.user_data.get('testing', False):
        await update.message.reply_text("檢測到未完成的測試，正在自動恢復...")
        asyncio.create_task(run_test(update, context))
    await update.message.reply_text(
        "歡迎使用增強版 URL 測試機器人！\n"
        "\n"
        "可用命令：\n"
        "\n"
        "基本功能：\n"
        "/start - 顯示歡迎訊息\n"
        "/seturl <網址> - 設置網址模板，例如 /seturl https://chiikawamarket.jp/cdn/shop/files/{}_1.jpg\n"
        "/setattempts <次數> - 設置測試次數，例如 /setattempts 10\n"
        "/setid <數字> - 設置初始數字，例如 /setid 4571609355900\n"
        "/test - 開始測試\n"
        "/pause - 暫停測試\n"
        "/resume - 繼續測試\n"
        "/stop - 停止測試\n"
        "/scheduletest <日期> <時間> <時區> - 設定定時測試，例如 /scheduletest 2025-05-10 14:30 GMT\n"
        "/stopschedule - 停止定時測試\n"
        "\n"
        "---\n"
        "\n"
        "圖片檢查功能：\n"
        "/setimagelinks <網址1>,<網址2>,... - 設置多個圖片網址，例如 /setimagelinks https://example.com/1.jpg,https://example.com/2.jpg\n"
        "/checkimages - 檢查圖片網址是否為 JPEG\n"
        "/scheduleimagecheck - 每小時檢查圖片網址\n"
        "/stopimagecheck - 停止每小時檢查\n"
    )

# Set URL command
async def set_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received seturl command")
    if not context.args:
        await update.message.reply_text("請提供網址！格式：/seturl <網址> 例如 /seturl https://chiikawamarket.jp/cdn/shop/files/{}_1.jpg")
        return
    url = context.args[0]
    context.user_data['url'] = url
    await save_test_state(context.user_data)
    await update.message.reply_text(f"網址已設置為：{url}")

# Set attempts command
async def set_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received setattempts command")
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("請提供有效數字！格式：/setattempts <次數> 例如 /setattempts 10")
        return
    attempts = int(context.args[0])
    context.user_data['attempts'] = attempts
    context.user_data['batch_number'] = 0
    await save_test_state(context.user_data)
    await update.message.reply_text(f"測試次數已設置為：{attempts}")

# Set initial number command
async def set_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received setid command")
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("請提供有效數字！格式：/setid <數字> 例如 /setid 4571609355900")
        return
    initial_number = int(context.args[0])
    context.user_data['initial_number'] = initial_number
    context.user_data['batch_number'] = 0
    await save_test_state(context.user_data)
    await update.message.reply_text(f"初始數字已設置為：{initial_number}")

# Test command
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received test command")
    if 'url' not in context.user_data or 'attempts' not in context.user_data:
        await update.message.reply_text("請先設置網址和測試次數！使用 /seturl 和 /setattempts")
        return
    if context.user_data.get('testing', False):
        await update.message.reply_text("測試已在進行！請先 /stop 或 /pause")
        return

    context.user_data['testing'] = True
    context.user_data['paused'] = False
    context.user_data['valid_urls'] = []
    context.user_data['current_index'] = 0
    context.user_data['batch_number'] = 0
    await save_test_state(context.user_data)

    asyncio.create_task(run_test(update, context))
    await update.message.reply_text("測試已開始！")

# Run test function with batch processing
async def run_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url_template = context.user_data['url']
    total_attempts = context.user_data['attempts']
    initial_number = context.user_data.get('initial_number', 4571609355900)
    batch_size = context.user_data.get('batch_size', 300)
    batch_number = context.user_data.get('batch_number', 0)

    try:
        start_index = batch_number * batch_size
        remaining_attempts = total_attempts - start_index
        if remaining_attempts <= 0:
            await update.message.reply_text("所有測試已完成！")
            return

        attempts_in_batch = min(batch_size, remaining_attempts)
        end_index = start_index + attempts_in_batch

        await update.message.reply_text(f"開始第 {batch_number + 1} 批測試（{start_index + 1} 到 {end_index}）")

        for i in range(start_index, end_index):
            if not context.user_data['testing']:
                break
            if context.user_data.get('paused', False):
                while context.user_data.get('paused', False) and context.user_data['testing']:
                    await asyncio.sleep(1)

            current_number = initial_number + i
            test_url = url_template.format(current_number)
            logger.info(f"Testing URL {test_url}")

            if await check_url(test_url):
                context.user_data['valid_urls'].append(test_url)
            context.user_data['current_index'] = i + 1

            # Save state and log resources every 200 tests or at the end of batch
            if (i + 1) % 200 == 0 or i + 1 == end_index:
                await save_test_state(context.user_data)
                log_resource_usage()

            await asyncio.sleep(1)

            # Update progress every 300 URLs (batch size)
            if (i + 1) % 300 == 0:
                await update.message.reply_text(f"進度：已完成 {i + 1}/{total_attempts} 次測試")

        # End of batch
        if context.user_data['testing']:
            valid_urls = context.user_data['valid_urls']
            if valid_urls:
                await update.message.reply_text(
                    f"第 {batch_number + 1} 批測試完成！以下是目前找到的有效網址：\n" + "\n".join(valid_urls)
                )
            else:
                await update.message.reply_text(f"第 {batch_number + 1} 批測試完成，沒有找到有效網址。")

            # Schedule next batch if there are more tests
            if end_index < total_attempts:
                context.user_data['batch_number'] = batch_number + 1
                await save_test_state(context.user_data)
                await update.message.reply_text("即將開始下一批測試...")
                await asyncio.sleep(10)
                await run_test(update, context)
            else:
                if valid_urls:
                    await update.message.reply_text(
                        "所有測試完成！以下是所有有效網址：\n" + "\n".join(valid_urls)
                    )
                else:
                    await update.message.reply_text("所有測試完成，沒有找到有效網址。")
                logger.info("All tests completed")

    except Exception as e:
        logger.error(f"Error during test: {e}")
        await update.message.reply_text(f"測試發生錯誤：{e}")
    finally:
        if context.user_data['current_index'] >= total_attempts:
            context.user_data['testing'] = False
            context.user_data['current_index'] = 0
            context.user_data['batch_number'] = 0
            await save_test_state(context.user_data)
            logger.info("Test state reset")

# Pause command
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received pause command")
    if not context.user_data.get('testing', False):
        await update.message.reply_text("沒有正在進行的測試！")
        return
    context.user_data['paused'] = True
    await save_test_state(context.user_data)
    await update.message.reply_text("測試已暫停。使用 /resume 繼續或 /stop 終止。")

# Resume command
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received resume command")
    if not context.user_data.get('testing', False):
        await update.message.reply_text("沒有正在進行的測試！")
        return
    if not context.user_data.get('paused', False):
        await update.message.reply_text("測試未暫停！")
        return
    context.user_data['paused'] = False
    await save_test_state(context.user_data)
    await update.message.reply_text("測試已繼續。")

# Stop command
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received stop command")
    if not context.user_data.get('testing', False):
        await update.message.reply_text("沒有正在進行的測試！")
        return
    context.user_data['testing'] = False
    context.user_data['current_index'] = 0
    context.user_data['batch_number'] = 0
    await save_test_state(context.user_data)
    valid_urls = context.user_data.get('valid_urls', [])
    if valid_urls:
        await update.message.reply_text(
            "測試已停止。以下是找到的有效網址：\n" + "\n".join(valid_urls)
        )
    else:
        await update.message.reply_text("測試已停止，沒有找到有效網址。")

# Schedule test command
async def schedule_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received scheduletest command")
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
        datetime_str = f"{date_str} {time_str}"
        scheduled_time = datetime.strptime(datetime_str, "%Y-%m-dd %H:%M")
        tz = pytz.timezone(timezone)
        scheduled_time = tz.localize(scheduled_time)
    except (ValueError, pytz.exceptions.UnknownTimeZoneError):
        await update.message.reply_text(
            "無效的日期、時間或時區！請使用格式：/scheduletest YYYY-MM-DD HH:MM TZ\n"
            "例如：/scheduletest 2025-05-10 14:30 GMT"
        )
        return

    context.user_data['scheduled_url'] = context.user_data['url']
    context.user_data['scheduled_attempts'] = context.user_data['attempts']
    context.user_data['scheduled_initial_number'] = context.user_data.get('initial_number', 4571609355900)
    context.user_data['scheduled_chat_id'] = update.effective_chat.id
    await save_test_state(context.user_data)

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
    logger.info("Running scheduled test")
    url_template = user_data['scheduled_url']
    attempts = user_data['scheduled_attempts']
    initial_number = user_data['scheduled_initial_number']
    chat_id = user_data['scheduled_chat_id']
    valid_urls = []

    try:
        for i in range(attempts):
            current_number = initial_number + i
            test_url = url_template.format(current_number)
            logger.info(f"Scheduled test: Testing URL {test_url}")

            if await check_url(test_url):
                valid_urls.append(test_url)
            await asyncio.sleep(1)

            if (i + 1) % 300 == 0:
                await bot.send_message(chat_id=chat_id, text=f"進度：已完成 {i + 1}/{attempts} 次測試")

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
        logger.info("Scheduled test completed")

    except Exception as e:
        logger.error(f"Error during scheduled test: {e}")
        await bot.send_message(chat_id=chat_id, text=f"定時測試發生錯誤：{e}")

# Stop scheduled test
async def stop_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received stopschedule command")
    if scheduler.get_job('scheduled_test'):
        scheduler.remove_job('scheduled_test')
        await update.message.reply_text("定時測試已取消。")
    else:
        await update.message.reply_text("沒有正在排程的定時測試。")

# Set image links command
async def set_image_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received setimagelinks command")
    try:
        if not context.args:
            await update.message.reply_text("請提供網址列表！格式：/setimagelinks <網址1>,<網址2>,... 例如 /setimagelinks https://example.com/1.jpg,https://example.com/2.jpg")
            return
        links = context.args[0].split(',')
        valid_links = [link.strip() for link in links if link.strip().startswith('http')]
        if not valid_links:
            await update.message.reply_text("請提供有效的網址！")
            return
        context.user_data['image_links'] = valid_links
        await save_test_state(context.user_data)
        await update.message.reply_text(f"已設置 {len(valid_links)} 個網址：\n" + "\n".join(valid_links))
    except Exception as e:
        logger.error(f"Error in set_image_links: {e}")
        await update.message.reply_text("發生錯誤，請稍後再試！")

# Check images command
async def check_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received checkimages command")
    if 'image_links' not in context.user_data:
        await update.message.reply_text("請先設置網址！使用 /setimagelinks")
        return

    valid_images = []
    for url in context.user_data['image_links']:
        if await check_url(url, check_image=True):
            valid_images.append(url)

    if valid_images:
        await update.message.reply_text(
            "檢查完成！以下是有效的 JPEG 圖片網址：\n" + "\n".join(valid_images)
        )
    else:
        await update.message.reply_text("檢查完成，沒有找到有效的 JPEG 圖片網址。")

# Schedule image check command
async def schedule_image_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received scheduleimagecheck command")
    if 'image_links' not in context.user_data:
        await update.message.reply_text("請先設置網址！使用 /setimagelinks")
        return

    context.user_data['image_check_chat_id'] = update.effective_chat.id
    scheduler.add_job(
        run_image_check,
        'interval',
        hours=1,
        args=[context.user_data, context.bot],
        id='image_check'
    )
    await update.message.reply_text("已設定每小時檢查圖片網址。使用 /stopimagecheck 停止。")

# Run scheduled image check
async def run_image_check(user_data, bot):
    logger.info("Running scheduled image check")
    valid_images = []
    for url in user_data['image_links']:
        if await check_url(url, check_image=True):
            valid_images.append(url)

    chat_id = user_data['image_check_chat_id']
    if valid_images:
        await bot.send_message(
            chat_id=chat_id,
            text="定時檢查完成！以下是有效的 JPEG 圖片網址：\n" + "\n".join(valid_images)
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text="定時檢查完成，沒有找到有效的 JPEG 圖片網址。"
        )

# Stop scheduled image check
async def stop_image_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received stopimagecheck command")
    if scheduler.get_job('image_check'):
        scheduler.remove_job('image_check')
        await update.message.reply_text("已停止每小時檢查圖片網址。")
    else:
        await update.message.reply_text("沒有正在進行的定時圖片檢查。")

# Setup Telegram bot handlers
def setup_bot():
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
    application.add_handler(CommandHandler("setimagelinks", set_image_links))
    application.add_handler(CommandHandler("checkimages", check_images))
    application.add_handler(CommandHandler("scheduleimagecheck", schedule_image_check))
    application.add_handler(CommandHandler("stopimagecheck", stop_image_check))

# Main coroutine to initialize the bot
async def initialize_bot():
    setup_bot()
    await application.initialize()

    # Set Telegram bot commands for the menu
    commands = [
        BotCommand("start", "顯示歡迎訊息"),
        BotCommand("seturl", "設置網址模板，例如 /seturl https://chiikawamarket.jp/cdn/shop/files/{}_1.jpg"),
        BotCommand("setattempts", "設置測試次數，例如 /setattempts 10"),
        BotCommand("setid", "設置初始數字，例如 /setid 4571609355900"),
        BotCommand("test", "開始測試"),
        BotCommand("pause", "暫停測試"),
        BotCommand("resume", "繼續測試"),
        BotCommand("stop", "停止測試"),
        BotCommand("scheduletest", "設定定時測試，例如 /scheduletest 2025-05-10 14:30 GMT"),
        BotCommand("stopschedule", "停止定時測試"),
        BotCommand("setimagelinks", "設置多個圖片網址，例如 /setimagelinks https://example.com/1.jpg,https://example.com/2.jpg"),
        BotCommand("checkimages", "檢查圖片網址是否為 JPEG"),
        BotCommand("scheduleimagecheck", "每小時檢查圖片網址"),
        BotCommand("stopimagecheck", "停止每小時檢查"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Telegram bot commands set successfully")

    # Check and set webhook
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    logger.info(f"Setting webhook to {webhook_url}")
    webhook_info = await application.bot.get_webhook_info()
    if webhook_info.url != webhook_url:
        logger.info("Webhook URL mismatch, resetting...")
        await application.bot.set_webhook(webhook_url)
    else:
        logger.info("Webhook already set correctly")

    await application.start()
    scheduler.start()
    logger.info("Bot and scheduler started successfully")

# Shutdown coroutine
async def shutdown():
    logger.info("Shutting down application")
    await application.stop()
    scheduler.shutdown()
    await application.bot.delete_webhook()
    logger.info("Shutdown complete")

# Uvicorn ASGI application with enhanced health check
async def app(scope, receive, send):
    if scope['type'] != 'http':
        return

    # Enhanced health check endpoint with timing
    if scope['path'] == '/health':
        start_time = time.time()
        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': [[b'content-type', b'text/plain']],
        })
        await send({
            'type': 'http.response.body',
            'body': b'OK',
        })
        logger.info(f"Health check completed in {time.time() - start_time:.3f} seconds")
        return

    # Webhook endpoint
    if scope['path'] != '/webhook':
        await send({
            'type': 'http.response.start',
            'status': 404,
            'headers': [[b'content-type', b'text/plain']],
        })
        await send({
            'type': 'http.response.body',
            'body': b'Not Found',
        })
        return

    if scope['method'] != 'POST':
        await send({
            'type': 'http.response.start',
            'status': 405,
            'headers': [[b'content-type', b'text/plain']],
        })
        await send({
            'type': 'http.response.body',
            'body': b'Method Not Allowed',
        })
        return

    try:
        body = b''
        more_body = True
        while more_body:
            message = await receive()
            body += message.get('body', b'')
            more_body = message.get('more_body', False)

        update_dict = json.loads(body.decode('utf-8'))
        update = Update.de_json(update_dict, application.bot)
        await application.process_update(update)

        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': [[b'content-type', b'text/plain']],
        })
        await send({
            'type': 'http.response.body',
            'body': b'OK',
        })

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        await send({
            'type': 'http.response.start',
            'status': 500,
            'headers': [[b'content-type', b'text/plain']],
        })
        await send({
            'type': 'http.response.body',
            'body': b'Internal Server Error',
        })

# Main execution
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(initialize_bot())
        port = int(os.getenv("PORT", 8080))
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            loop="asyncio",
            log_level="info",
            lifespan="on"
        )
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())
    except KeyboardInterrupt:
        loop.run_until_complete(shutdown())
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        loop.run_until_complete(shutdown())
    finally:
        loop.close()