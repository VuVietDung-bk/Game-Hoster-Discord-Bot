import os
import logging
import webserver

from dotenv import load_dotenv

from bot import MinigameBot

if __name__ == "__main__":
    load_dotenv()
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    if not TOKEN:
        print("⚠️ Vui lòng set biến môi trường DISCORD_BOT_TOKEN")
        print("Ví dụ: export DISCORD_BOT_TOKEN='your_token_here'")
    else:
        handler = logging.FileHandler(
            filename="discord.log", encoding="utf-8", mode="w"
        )
        bot = MinigameBot()
        webserver.keep_alive()
        bot.run(TOKEN, log_handler=handler, log_level=logging.DEBUG)
