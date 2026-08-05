import logging
import pathlib
import sys
from pytz import timezone
from models import *
import orjson

db = Database()


class StreamObject:
    def __init__(self, online=False, timestamp_start=0, title="",
                 category="", viewers_str="", viewers_int=0, thumbnail_url="",
                 stream_id="", user_id=""):
        self.online = online
        self.timestamp_start = timestamp_start
        self.title = title
        self.category = category
        self.viewers_str = viewers_str
        self.viewers_int = viewers_int
        self.thumbnail_url = thumbnail_url
        self.stream_id = stream_id
        self.user_id = user_id


class AlertObject:
    def __init__(self, user_id, text, channel_name, change_data, photo_url=None, url_button=None):
        self.user_id = user_id
        self.text = text
        self.channel_name = channel_name
        self.change_data = change_data
        self.photo_url = photo_url
        self.log_data = f"{get_user_name(user_id)}: {channel_name} - {change_data}"
        self.url_button = url_button


class MessageObject:
    def __init__(self, operation, user_id, text, markup=None, is_bold=False, photo=None, message_id=None, kwargs=None):
        self.operation = operation
        self.user_id = user_id
        self.text = text
        self.markup = markup
        self.is_bold = is_bold
        self.photo = photo
        self.message_id = message_id
        self.kwargs = {} if kwargs is None else kwargs
        self.user_name = get_user_name(user_id)


class Config:
    def __init__(self):
        self.absolute_path = str(pathlib.Path(__file__).parent.resolve())
        self.data_folder = f"{self.absolute_path}/data"

        session = db.get_session()
        try:
            config_data = {row.key: row.value for row in session.query(DBConfig).all()}

            self.bot_token = config_data.get("bot_token", "")
            self.update_time = int(config_data.get("update_time", 30))
            self.streamers_in_page = int(config_data.get("streamers_in_page", 10))
            self.stream_titles_in_page = int(config_data.get("stream_titles_in_page", 25))
            self.streamers_limit_by_user = int(config_data.get("streamers_limit_by_user", 15))
            self.webhook_url = config_data.get("webhook_url", "")
            self.webhook_path = config_data.get("webhook_path", "")
            self.twitch_user_pattern = config_data.get("twitch_user_pattern", r"^[a-zA-Z0-9_]{1,25}$")
            self.time_range_pattern = config_data.get("time_range_pattern",
                                                      r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]-(?:[01][0-9]|2[0-3]):[0-5]["
                                                      r"0-9]$")
            self.url_stream = config_data.get("url_stream", "https://api.twitch.tv/helix/streams")
            self.url_token = config_data.get("url_token", "https://id.twitch.tv/oauth2/token")
            self.url_videos = config_data.get("url_videos", "https://api.twitch.tv/helix/videos")
            self.oauth = config_data.get("oauth", "")
            self.client_id = config_data.get("client_id", "")
            self.client_secret = config_data.get("client_secret", "")
            self.main_events = config_data.get("main_events", ["in_streamer_list"])

            self.logs = config_data.get("logs", "")
            self.user_info = config_data.get("user_info", "")

            self.language = {}
            for lang in session.query(Language).all():
                self.language[lang.code] = {
                    "flag": lang.flag,
                    "name": lang.name,
                    **lang.data
                }

            self.stop_registration = bool(int(config_data.get("stop_registration", 0)))

            self.admins = [str(admin.id) for admin in session.query(Admin).all()]

            stats = {stat.name: stat.value for stat in session.query(Stat).all()}
            self.total_alerts = stats.get("total_alerts", 0)

        finally:
            session.close()

        self.params_to_get_oauth = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        self.head = {
            "Authorization": f"Bearer {self.oauth}",
            "Client-Id": self.client_id
        }

    def update_config(self):
        self.__init__()


def get_user_name(user_id):
    session = db.get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user and user.username:
            return f"@{user.username}"
        return user_id
    finally:
        session.close()


def deserialize_func(x):
    return orjson.loads(x)


config = Config()
sys.stderr = open(f"{config.data_folder}/errors.log", "a")
tz = timezone("Europe/Moscow")
logging.Formatter.converter = lambda *args_converter: datetime.now(tz=tz).timetuple()
logging.basicConfig(
    level=logging.INFO,
    filename=f"{config.data_folder}/py_log.log",
    filemode="a",
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="UTF-8"
)
logging.getLogger("aiogram").setLevel(logging.WARNING)

streams = {}
users_to_delete_queue = []
messages_queue = []
