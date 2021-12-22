import random
import time

from loguru import logger

from . import spotify, twitter
from .config import Config
from .image.generate import generate_image
from .twitter import update_twitter_banner
from .utils import get_song_info

# Get top tracks.
top_tracks = spotify.top_tracks(limit=5)

top_tracks = [track for track in top_tracks["items"]]

# Get song info with switch to recently played if no song is playing.
song, is_playing = get_song_info(spotify=spotify)

# Get the status.
status = random.choice(Config.STATUS_MAPPING[is_playing]) + ":"

# Update banner every 5 minutes, until stopped.
while True:
    # Generate the spotify banner image.
    generate_image(status, is_playing, song, top_tracks, Config.IMAGE_PATH)

    # Update the banner
    update_twitter_banner(twitter)
    logger.info("Updated twitter banner.")

    # Sleep for 5 minutes.
    logger.info("Sleeping for 5 minutes.")
    time.sleep(5 * 60)
