import sys, os, logging

from dotenv import load_dotenv
from .bot import Bot
load_dotenv()

logger = logging.getLogger(__name__)

_m = sys.modules[__name__]
_m.bot = None

def configure():
    logging.basicConfig(level=os.environ.get("BEACHBOT_LOGLEVEL", "DEBUG"))

def get_bot():
    return _m.bot

def start_bot():
    logger.info("Starting bot")
    import ctypes.util, discord

    logger.info("Finding and loading opus")
    discord.opus.load_opus(ctypes.util.find_library('opus'))

    if not _m.bot:
        _m._bot = Bot(os.getenv('BEACHBOT_TOKEN'))

    _m._bot.start()