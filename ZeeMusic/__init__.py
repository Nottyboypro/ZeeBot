from ZeeMusic.core.bot import Zee
from ZeeMusic.core.dir import dirr
from ZeeMusic.core.git import git
from ZeeMusic.core.userbot import Userbot
from ZeeMusic.misc import dbb, heroku

from .logging import LOGGER

dirr()
git()
dbb()
heroku()

app = Zee()
userbot = Userbot()


from .platforms import *

Apple = AppleAPI()
Carbon = CarbonAPI()
SoundCloud = SoundAPI()
Spotify = SpotifyAPI()
Resso = RessoAPI()
Telegram = TeleAPI()
YouTube = YouTubeAPI()

