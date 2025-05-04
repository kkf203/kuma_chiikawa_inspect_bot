import asyncio
import logging
import re
from urllib.parse import urljoin

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variables
TOKEN = "7928836301:AAHlTTCy0QFJ9lNz3kRMgR66-BfXfDA6ErM"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message with example."""
    example_url = "https://chiikawamarket.jp/cdn/shop/files/{}_1.jpg"
    example_id = "4571609355854"
    example_attempts = 5
    await update.message.reply_text(
        f"Welcome to URL Tester Bot!\n\n"
        f"1. Set URL template with /seturl {example_url}\n"
        f"2. Set starting ID with /setid {example_id}\n"
        f"3. Set number of attempts with /setattempts {example_attempts}\n"
        f"4. Run test with /test\n"
        f"5. Stop test with /stop\n\n"
        f"Use the menu button to see all commands."
    )

async def set_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the URL template."""
    if context.args:
        context.user_data["url_template"] = context.args[0]
        await update.message.reply_text(f"URL template set to: {context.user_data['url_template']}")
    else:
        await update.message.reply_text("Please provide a URL template. Example: /seturl https://example.com/{}_1.jpg")

async def set_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the starting ID."""
    if context.args and context.args[0].isdigit():
        context.user_data["start_id"] = int(context.args[0])
        await update.message.reply_text(f"Starting ID set to: {context.user_data['start_id']}")
    else:
        await update.message.reply_text("Please provide a valid numeric ID. Example: /setid 12345")

async def set_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the number of attempts."""
    if context.args and context.args[0].isdigit():
        context.user_data["attempts"] = int(context.args[0])
        await update.message.reply_text(f"Number of attempts set to: {context.user_data['attempts']}")
    else:
        await update.message.reply_text("Please provide a valid number of attempts. Example: /setattempts 5")

async def check_url(client: httpx.AsyncClient, url: str) -> tuple[bool, str]:
    """Check if the URL is valid."""
    try:
        response = await client.get(url, follow_redirects=True)
        if response.status_code == 200:
            content = response.text.lower()  # Convert to lowercase for case-insensitive checks
            # Check for invalid page indicators
            if (
                "the page you’re looking for couldn’t be found." in content
                or "not found" in content
                or "404error" in content
            ):
                return False, url
            return True, url
        return False, url
    except httpx.RequestError as e:
        logger.error(f"Error checking URL {url}: {e}")
        return False, url

async def run_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run the URL test."""
    if context.user_data.get("testing", False):
        await update.message.reply_text("Test is already running! Use /stop or /pause to manage it.")
        return

    # Check if required parameters are set
    if "url_template" not in context.user_data:
        await update.message.reply_text("Please set the URL template first with /seturl")
        return
    if "start_id" not in context.user_data:
        await update.message.reply_text("Please set the starting ID first with /setid")
        return
    if "attempts" not in context.user_data:
        await update.message.reply_text("Please set the number of attempts first with /setattempts")
        return

    context.user_data["testing"] = True
    url_template = context.user_data["url_template"]
    start_id = context.user_data["start_id"]
    attempts = context.user_data["attempts"]
    valid_urls = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for i in range(attempts):
                if not context.user_data.get("testing", False):
                    await update.message.reply_text("Test stopped.")
                    break

                current_id = start_id + i
                url = url_template.format(current_id)
                logger.info(f"Testing URL {url}")
                is_valid, tested_url = await check_url(client, url)

                if is_valid:
                    valid_urls.append(tested_url)

                # Send progress update every 10 URLs
                if (i + 1) % 10 == 0:
                    await update.message.reply_text(f"Tested {i + 1}/{attempts} URLs. Found {len(valid_urls)} valid URLs so far.")

                # Small delay to avoid overwhelming the server
                await asyncio.sleep(1)

        # Send final result
        if valid_urls:
            result = "Test completed! Found the following valid URLs:\n" + "\n".join(valid_urls)
        else:
            result = "Test completed. No valid URLs found."
        await update.message.reply_text(result)

    except Exception as e:
        logger.error(f"Test failed: {e}")
        await update.message.reply_text(f"Test failed due to an error: {e}")
    finally:
        context.user_data["testing"] = False
        logger.info("Test completed")
        logger.info("Test state reset")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop the running test."""
    if context.user_data.get("testing", False):
        context.user_data["testing"] = False
        await update.message.reply_text("Test stopping... Please wait for the current operation to complete.")
    else:
        await update.message.reply_text("No test is currently running.")

async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Health check endpoint."""
    await update.message.reply_text("OK")

def main() -> None:
    """Run the bot."""
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("seturl", set_url))
    application.add_handler(CommandHandler("setid", set_id))
    application.add_handler(CommandHandler("setattempts", set_attempts))
    application.add_handler(CommandHandler("test", run_test))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("health", health))

    # Start the bot
    application.run_polling(timeout=10, poll_interval=1.0)

async def post_init(application: Application) -> None:
    """Set bot commands after initialization."""
    commands = [
        ("start", "Start the bot and show instructions"),
        ("seturl", "Set the URL template"),
        ("setid", "Set the starting ID"),
        ("setattempts", "Set the number of attempts"),
        ("test", "Run the URL test"),
        ("stop", "Stop the running test"),
        ("health", "Check bot health"),
    ]
    await application.bot.set_my_commands([(cmd, desc) for cmd, desc in commands])
    logger.info("Bot commands set")

if __name__ == "__main__":
    main()