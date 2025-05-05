# Gunicorn configuration file
from telegram_url_tester_enhanced import post_fork

# Hook to run Telegram bot after worker fork
post_fork = post_fork