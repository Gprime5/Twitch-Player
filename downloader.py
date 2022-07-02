from functools import lru_cache
from queue import Queue
from threading import Thread
import json
import logging
import os
import requests
import time
import shutil

from PIL import Image

logging.basicConfig(
    style="{",
    level=logging.INFO,
    format="[{levelname}] {asctime} {module} | {message}",
    datefmt='%H:%M:%S'
)

for folder in ("Files", "twitch_emotes", "badges", "bttv_emotes", "ffz_emotes", "7tv_emotes"):
    os.makedirs(folder, exist_ok=True)

def format_time(seconds):
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    
    return f"{hours:0>2.0f}:{minutes:0>2.0f}:{seconds:0>2.0f}"

class Info(dict):
    def __init__(self):
        self.update({
            "files": {},
            "client_id": "",
            "current_folder": __file__.rsplit("\\", 1)[0],
            "volume": 100
        })
        
        try:
            with open("info.json") as fp:
                self.update(json.load(fp))
        except FileNotFoundError:
            self.save()
    
    def save(self):
        logging.info("Saving info")
        with open("info.json", "w") as fp:
            json.dump(self, fp, indent=4, sort_keys=True)

info = Info()
session = requests.Session()
thread_queue = Queue()

def http_thread():
    cache = {}
    
    while True:
        items = thread_queue.get()
        
        logging.info(f"http_thread: {items}")
        
        callback, _type, values = items
        
        if items in cache and time.time() - cache[items]["time"] < 30 * 60:
            logging.info(f"http_thread cache: {items}")
            callback(cache[items]["output"])
            continue
        
        if _type == "video":
            values = dict(values)
            
            video = VideoData(values["id"])
            video.update(values)
            video.save()
            
            cache[items] = {
                "time": time.time(),
                "output": video
            }
            
            callback(video)
        elif _type == "past_broadcasts":
            login, cursor = values
            
            parameters = [
                {
                    "operationName":"FilterableVideoTower_Videos",
                    "variables": {
                        "limit":10,
                        "channelOwnerLogin": login,
                        "broadcastType":"ARCHIVE",
                        "cursor": cursor,
                        "videoSort":"TIME"
                    },
                    "extensions": {
                        "persistedQuery": {
                            "version":1,
                            "sha256Hash":"a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb"
                        }
                    }
                }
            ]
            
            response = session.post("https://gql.twitch.tv/gql", json=parameters)
            if response.status_code == 200:            
                cache[items] = {
                    "time": time.time(),
                    "output": response
                }
                
                callback(response)
            elif response.status_code == 400:
                if response.json()["message"] == 'The \"Client-ID\" header is missing from the request.':
                    logging.error("valid Client ID required")
                    callback("Valid Client ID required")
        elif _type == "preview":
            response = session.get(values)
            
            if response.status_code == 200:
                cache[items] = {
                    "time": time.time(),
                    "output": response
                }
                callback(200, values, response.content)
            elif response.status_code == 400:
                if response.json()["message"] == 'The \"Client-ID\" header is missing from the request.':
                    logging.error("valid Client ID required")
            else:
                cache[items] = {
                    "time": time.time(),
                    "output": response
                }
                callback(response.status_code, values)

download_queue = Queue()
def download_thread():
    while True:
        callback, video, speed_var, downloading_var = download_queue.get()
        logging.info(f"Downloading start | {downloading_var.get()=} / {video['id']=}")
        try:
            for i in download_video(video, speed_var):
                if downloading_var.get() != video["id"]:
                    break
                
                callback(video, i)
        except (ConnectionAbortedError, ConnectionResetError):
            logging.info("Connection Error")
        
        logging.info(f"Downloading end | {downloading_var.get()=} / {video['id']=}")
        
        callback(video)

def download_video(video, speed_var):
    yield "Downloading"
    
    if not os.path.exists(f"Files/{video['id']}/chat.txt"):
        logging.info(f"Downloading chat - {video['id']}")
        yield from chat(video)
    
    video_folder = f"{info['files'].get(video['id'], info['current_folder'])}/Files/{video['id']}"
    os.makedirs(video_folder, exist_ok=True)
    
    logging.info(f"Downloading video - {video['id']}")
    logging.info(f"Downloaded: {video['downloaded']} / Total: {len(video['vod_parts'])}")
    
    while video["downloaded"] < len(video["vod_parts"]):
        yield "Downloading"
        url = f"{video['url']}/{video['vod_parts'][video['downloaded']]}"
        response = requests.get(url, stream=True)
        parts = []
        chunk = 1
        
        while chunk:
            time.sleep(.001)
            yield "Downloading"
            chunk = response.raw.read(int(speed_var.get()))
            parts.append(chunk)
        yield "Downloading"
        with open(f"{video_folder}/video.mp4", "ab") as fp:
            fp.write(b"".join(parts))
        
        video["downloaded"] += 1
        video.save()
        
Thread(target=http_thread, daemon=True).start()
Thread(target=download_thread, daemon=True).start()

def http(*args):
    thread_queue.put(args)

def download(*args):
    download_queue.put(args)

class VideoData(dict):
    videos = {}
    
    def __init__(self, video_id):
        video_id = str(video_id)
        
        try:
            with open(f"Files/{video_id}/data.txt") as fp:
                self.update(json.load(fp))
        except (FileNotFoundError, KeyError):
            info["files"][video_id] = info["current_folder"]

            parameters = [
                {
                    "operationName": "PlaybackAccessToken_Template",
                    "query": """query PlaybackAccessToken_Template($login: String!, $isLive: Boolean!, $vodID: ID!, $isVod: Boolean!, $playerType: String!) {  streamPlaybackAccessToken(channelName: $login, params: {platform: "web", playerBackend: "mediaplayer", playerType: $playerType}) @include(if: $isLive) {    value    signature    __typename  }  videoPlaybackAccessToken(id: $vodID, params: {platform: "web", playerBackend: "mediaplayer", playerType: $playerType}) @include(if: $isVod) {    value    signature    __typename  }}""",
                    "variables": {
                        "isLive": False,
                        "login": "",
                        "isVod": True,
                        "vodID": video_id,
                        "playerType": "site"
                    }
                },
                {
                    "operationName": "NielsenContentMetadata",
                    "variables": {
                        "isCollectionContent": False,
                        "isLiveContent": False,
                        "isVODContent": True,
                        "collectionID": "",
                        "login": "",
                        "vodID": video_id
                    },
                    "extensions": {
                        "persistedQuery": {
                            "version": 1,
                            "sha256Hash": "2dbf505ee929438369e68e72319d1106bb3c142e295332fac157c90638968586"
                        }
                    }
                }
            ]
            
            response = session.post("https://gql.twitch.tv/gql", json=parameters)
            
            auth, user_data = response.json()
            
            token = auth["data"]["videoPlaybackAccessToken"]
            user_data = user_data["data"]["video"]
            
            url = f"https://usher.ttvnw.net/vod/{video_id}.m3u8"
            params = {
                "allow_source": "true",
                "sig": token['signature'],
                "token": token["value"]
            }
            
            list_url = requests.get(url, params).text.split("\n")
            video_data = requests.get(list_url[4]).text.split("\n")
            
            self.update({
                "downloaded": 0,
                "played": 0,
                "id": video_id,
                "title": user_data["title"],
                
                "user_id": user_data["owner"]["id"],
                "user_name": user_data["owner"]["login"],
                "estimated_part_size": int(list_url[3].split(",")[0].split("=")[1])/.8,
                
                "part_duration": float(video_data[2].split(":")[1]),
                "total_duration": float(video_data[7].split(":")[1]),
                "url": list_url[4].rsplit("/", 1)[0],
                "vod_parts": [v for v in video_data[9:-1:2] if v != "#EXT-X-TWITCH-DISCONTINUITY"]
            })
        
        self.videos[video_id] = self
    
    @property
    def values(self):
        played = f"{format_time(self['played'])} / {format_time(self['total_duration'])}"
        
        return (
            self["user_name"],
            self["title"],
            f"{self['downloaded'] / len(self['vod_parts']):.2%}",
            played
        )
    
    def save(self):
        os.makedirs(f"Files/{self['id']}", exist_ok=True)
        
        with open(f"Files/{self['id']}/data.txt", "w") as fp:
            json.dump(self, fp, indent=4, sort_keys=True)
    
    def delete(self):
        shutil.rmtree(f"Files/{self['id']}")
        
        try:
            shutil.rmtree(f"{info['files'][self['id']]}/Files/{self['id']}")
        except FileNotFoundError:
            pass
        
        del info["files"][self["id"]]
        del self.videos[self["id"]]

class Gif():
    """
    This class represents a Gif object.
    The class is given a PIL.Image object and unpacks the frames into a list.
    
    Valid Image formats are "GIF" and "WEBM".
    Some WEBM Gifs do not have a duration so it is defaulted to 40ms
    Some WEBM Gifs have a duration of 0 so it is defaulted to 40ms.
    """
    
    def __init__(self, image, duration=40):
        self.imarray = []
        for i in range(image.n_frames):
            image.seek(i)
            self.imarray.append(image.convert("RGBA"))
        self.duration = image.info.get("duration", duration) or duration
        self.width, self.height = image.size
    
    def __getitem__(self, time):
        """Returns the frame corresponding to the time in seconds."""
        
        return self.imarray[int(time * 1000 / self.duration % len(self.imarray))]

class BaseCache():
    def __init__(self, video, update, folder, user, global_url, channel_url, emote_url):
        self.emote_url = emote_url
        self.folder = folder
        
        try:
            with open(f"{folder}/global.txt") as fp:
                global_emotes = json.load(fp)
                
            with open(f"{folder}/{video[user]}.txt") as fp:
                channel_emotes = json.load(fp)
        except FileNotFoundError:
            pass
            
        if update:
            global_emotes.update(self.parse(session.get(global_url).json()))
            with open(f"{folder}/global.txt", "w") as fp:
                json.dump(global_emotes, fp, indent=4, sort_keys=True)
            
            channel_emotes.update(self.parse(session.get(channel_url.format(video[user])).json()))
            with open(f"{folder}/{video[user]}.txt", "w") as fp:
                json.dump(channel_emotes, fp, indent=4, sort_keys=True)
            
        self.emotes = {**global_emotes, **channel_emotes}
        
    def __contains__(self, item):
        return item in self.emotes

    @lru_cache(maxsize=None)
    def __call__(self, word):
        # Function for saving emotes
        
        if word not in self.emotes:
            return
            
        filename = f"{self.folder}/{self.emotes[word]}"
        if os.path.exists(filename):
            return
            
        with open(filename, "wb") as fp:
            url = self.emote_url.format(self.emotes[word].split(".")[0])
            fp.write(session.get(url).content)
    
    @lru_cache(maxsize=None)
    def __getitem__(self, word):
        # Function for getting emote images
        
        filename = f"{self.folder}/{self.emotes[word]}"
        
        if not os.path.exists(filename):
            self(word)
            
        image = Image.open(filename)
        if image.format in ("WEBP", "GIF"):
            return Gif(image)
        return image.convert("RGBA")

class BadgeCache(BaseCache):
    def __init__(self, video, update=False):
        super().__init__(video, update, "badges", "user_id",
            "https://badges.twitch.tv/v1/badges/global/display",
            "https://badges.twitch.tv/v1/badges/channels/{}/display",
            "https://static-cdn.jtvnw.net/badges/v1/{}/1"
        )
        
    def parse(self, response):
        return {
            f"{set_name}/{version}": data["image_url_1x"].split("/")[-2] + ".png"
            for set_name, versions in response["badge_sets"].items()
            for version, data in versions["versions"].items()
        }

class BttvCache(BaseCache):
    def __init__(self, video, update=False):
        super().__init__(video, update, "bttv_emotes", "user_id",
            "https://api.betterttv.net/3/cached/emotes/global",
            "https://api.betterttv.net/3/cached/users/twitch/{}",
            "https://cdn.betterttv.net/emote/{}/1x"
        )
    
    def parse(self, response):
        if isinstance(response, dict):
            return {
                item["code"]: f"{item['id']}.{item['imageType']}"
                for group in (response["channelEmotes"], response["sharedEmotes"])
                for item in group
            }
        
        return {item["code"]: f"{item['id']}.{item['imageType']}" for item in response}
        
class FfzCache(BaseCache):
    def __init__(self, video, update=False):
        super().__init__(video, update, "ffz_emotes", "user_id",
            "https://api.frankerfacez.com/v1/set/global",
            "https://api.frankerfacez.com/v1/room/id/{}",
            "https://cdn.frankerfacez.com/emote/{}/1"
        )
    
    def parse(self, response):
        return {
            item["name"]: item["urls"]["1"].split("/")[4] + ".png"
            for item in list(response["sets"].values())[0]["emoticons"]
        }
        
class _7tvCache(BaseCache):
    def __init__(self, video, update=False):
        super().__init__(video, update, "7tv_emotes", "user_name",
            "https://api.7tv.app/v2/emotes/global",
            "https://api.7tv.app/v2/users/{}/emotes",
            'https://cdn.7tv.app/emote/{}/1x'
        )
        
    def parse(self, response):
        # response will be a dictionary if the streamer doesn't have 7tv emotes
        return {
            item["name"]: f'{item["id"]}.{item["mime"].split("/")[1]}'
            for item in response
        } if isinstance(response, list) else {}

@lru_cache(maxsize=None)
def twitch_emote(emoticon_id):
    """Function for saving Twitch emotes."""
    
    filename = f"twitch_emotes/{emoticon_id}.png"
    if os.path.exists(filename):
        return
        
    url = f"https://static-cdn.jtvnw.net/emoticons/v1/{emoticon_id}/1.0"
    with open(filename, "wb") as fp:
        fp.write(session.get(url).content)

def chat(video):
    # Downloads the Twitch chat.
    
    url = f"https://api.twitch.tv/v5/videos/{video['id']}/comments"
    parameters = {"content_offset_seconds": 0}
    
    comments = []
    badge_cache = BadgeCache(video, True)
    emote_caches = (BttvCache(video, True), FfzCache(video, True), _7tvCache(video, True))
    
    while True:
        response = session.get(url, params=parameters).json()
        
        for item in response["comments"]:
            data = {
                "name": item["commenter"]["display_name"],
                "offset": item["content_offset_seconds"]
            }
            
            message = item["message"]
            
            data["badges"] = message.get("user_badges", ())
            for badge in data["badges"]:
                badge_cache(f'{badge["_id"]}/{badge["version"]}')
                    
            data["color"] = message.get("user_color")
                
            if message.get("fragments"):
                data["fragments"] = []
                
                for fragment in message["fragments"]:
                    if fragment.get("emoticon"):
                        data["fragments"].append({
                            "emoticon": fragment["emoticon"]["emoticon_id"]
                        })
                        twitch_emote(fragment["emoticon"]["emoticon_id"])
                    else:
                        data["fragments"].append(fragment)
                        for word in fragment["text"].split():
                            for emote_cache in emote_caches:
                                emote_cache(word)
            else:
                # message doesn't have a fragment if it is a highlighted message.
                
                data["fragments"] = message["body"]   
            
            comments.append(json.dumps(data))
            
        yield len(comments)
            
        if response.get("_next"):
            parameters = {"cursor": response["_next"]}
        else:
            break
    
    with open(f"Files/{video['id']}/chat.txt", "w") as fp:
        fp.write("\n".join(comments))