from functools import partial, lru_cache
from queue import Queue, Full
from random import choice
from threading import Thread
from itertools import groupby, cycle
from json import loads
from time import time, sleep
import logging

from PIL import Image, ImageFont, ImageDraw, ImageTk

import downloader

try:
    FONT = ImageFont.truetype("tahomabd.ttf", 12)
except OSError:
    FONT = ImageFont.truetype("arialbd.ttf", 12)

DEFAULT_COLORS = [
    "#0000FF", # Blue
    "#FF7F50", # Coral
    "#005A9C", # DodgerBlue
    "#00FF7F", # SpringGreen
    "#9ACD32", # YellowGreen
    "#00FF00", # Green
    "#FF4500", # OrangeRed
    "#FF0000", # Red
    "#DAA520", # GoldenRod
    "#FF69B4", # HotPink
    "#5F9EA0", # CadetBlue
    "#2E8B57", # SeaGreen
    "#D2691E", # Chocolate
    "#8A2BE2", # BlueViolet
    "#B22222", # Firebrick
]

background_colors = cycle(("#1f1925", "#19171c"))
PADX, PADY = 5, 5
LINE_HEIGHT = 25
chat_width = 340

textsize = lru_cache(maxsize=None)(
    partial(ImageDraw.Draw(Image.new("RGB", (0, 0))).textsize, font=FONT)
)

@lru_cache(maxsize=None)
def name_cache(name, color=None):
    image = Image.new("RGBA", textsize(name))
    ImageDraw.Draw(image).text((0, 0), name, fill=color or choice(DEFAULT_COLORS), font=FONT)
    
    return image

@lru_cache(maxsize=None)
def twitch_emote(emote_id):
    return Image.open(f"twitch_emotes/{emote_id}.png").convert("RGBA")

class BadgeCache(downloader.BadgeCache):
    @lru_cache(maxsize=None)
    def __getitem__(self, code):
        image = Image.new("RGBA", (20, 21))
        badge = Image.open(f"badges/{self.emotes[code]}").convert("RGBA")
        image.paste(badge, (0, 0), badge)
            
        return image

class Chat(Thread):
    """Class for drawing the chat."""
    def __init__(self, video, canvas):
        super().__init__(daemon=True)
        
        with open(f"Files/{video['id']}/chat.txt") as fp:
            self.data = [loads(line.rstrip("\n")) for line in fp]
        
        self.canvas = canvas
        self.seek(0)
        
        self.queue = Queue(maxsize=1)
        
        self.badge_cache = BadgeCache(video)
        self.bttv_cache = downloader.BttvCache(video)
        self.ffz_cache = downloader.FfzCache(video)
        self._7tv_cache = downloader._7tvCache(video)
        
        self.start()
        
        logging.info(f"Chat start: {video['id']}")
        
    def __call__(self, timestamp):
        try:
            self.queue.put_nowait(timestamp)
        except Full:
            pass
    
    def run(self):
        while True:
            self.canvas.set_image(ImageTk.PhotoImage(self.draw(self.queue.get())))
            sleep(.02)
            
    def seek(self, timestamp):
        # Clear the current frame
        self.base = Image.new("RGBA", (chat_width, 2000), "#33393b")
        self.gifs = []
        self.counter = 0
        
        # Loads up to 30 messages before timestamp
        while self.data[self.counter]["offset"] < timestamp:
            self.counter += 1
        self.counter -= 30
        self.current = self.data[self.counter]
    
    def draw(self, timestamp):
        if timestamp >= self.current["offset"]:
            # Draw badges
            message = [[
                self.badge_cache[f'{data["_id"]}/{data["version"]}']
                for data in self.current.get("badges", ())
            ]]
            
            # Draw name
            message[-1].append(name_cache(self.current["name"], self.current["color"]))
            line_width = sum(item.width for item in message[-1]) + textsize(": ")[0] + PADX*2
            message[-1].append(": ")
            
            def update(image, width=None):
                if width is None:
                    width = image.width
                
                nonlocal line_width
                
                if line_width + width > chat_width:
                    message.append([])
                    line_width = PADX * 2
                    
                message[-1].append(image)
                line_width += width
            
            for fragment in self.current["fragments"]:
                if isinstance(fragment, str):
                    c = fragment
                else:
                    if fragment.get("emoticon"):
                        try:
                            try:
                                update(twitch_emote(fragment["emoticon"]))
                            except FileNotFoundError:
                                logging.error(f"Emote not found: {fragment['emoticon']}")
                                downloader.twitch_emote(fragment["emoticon"])
                                update(twitch_emote(fragment["emoticon"]))
                            continue
                        except downloader.requests.exceptions.ConnectionError:
                            logging.error(f"Connection Error")
                    
                    c = fragment["text"]
                
                while c:
                    # Using partition instead of split because I want to keep the spaces
                    a, b, c = c.partition(" ")
                    for word in (a, b):
                        if word == "":
                            continue
                        
                        for emote_cache in (self.bttv_cache, self.ffz_cache, self._7tv_cache):
                            if word in emote_cache:
                                update(emote_cache[word])
                                break
                        else:
                            while True:
                                width = textsize(word)[0]
                                if width > chat_width:
                                    # Split long words over chat_width pixels wide
                                    for i in range(len(word)):
                                        width = textsize(word[:i+1])[0]
                                        if width > chat_width:
                                            left, word = word[:i], word[i:]
                                            update(left, textsize(left)[0])
                                            break
                                else:
                                    update(word, width)
                                    break
            
            ######################### Draw message
            
            background = next(background_colors)
            
            block = Image.new(
                "RGB",
                (chat_width, PADY*2 + LINE_HEIGHT*len(message)),
                background
            )
            img_draw = ImageDraw.Draw(block)
            
            self.gifs = [(*_, y + block.height) for *_, y in self.gifs if y < 2000]
            
            for row_index, row in enumerate(message):
                x = PADX
                for item in row:
                    n = PADY + LINE_HEIGHT*row_index
                    if isinstance(item, str):
                        width, height = textsize(item)
                        img_draw.text(
                            (x, n + (LINE_HEIGHT - height)//2),
                            item,
                            fill="#dad8da",
                            font=FONT    
                        )
                        x += width
                    elif isinstance(item, downloader.Gif):
                        self.gifs.append((
                            item,
                            background,
                            x,
                            block.height - n - (LINE_HEIGHT - item.height)//2
                        ))
                        x += item.width
                    else:
                        block.paste(
                            item,
                            (x, n - item.height//2 + 12),
                            item
                        )
                        x += item.width
            
            # Moves the base image up by the height of the current block
            self.base = self.base.transform(
                (self.base.size[0], 2000),
                Image.AFFINE,
                # Copied online, not sure how this corresponds to the transformation
                (1, 0, 0, 0, 1, block.height)
            )
            self.base.paste(block, (0, self.base.height - block.height))
            
            self.counter += 1
            if self.counter < len(self.data):
                self.current = self.data[self.counter]
            else:
                self.current = {"offset": float("inf")}
            
        for gif, background, x, y in self.gifs:
            # Draws Gifs by covering up the old frame of the gif,
            # then pasting the new frame on top.
            
            image = gif[time()]
            cover = Image.new("RGB", image.size, background)
            self.base.paste(cover, (x, self.base.height - y))
            self.base.paste(image, (x, self.base.height - y), image)
        
        return self.base