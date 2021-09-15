import os

class Player:
    volume = int(os.getenv("BEACHBOT_DEFAULT_VOLUME", "30"))