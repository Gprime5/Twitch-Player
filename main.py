from tkinter import BooleanVar, ttk, TclError, messagebox, Tk
from datetime import datetime
import io
import os
import time
import traceback
import logging

from PIL import ImageTk, Image
import vlc

from chat import Chat
from layout import Layout
import downloader

format_time = downloader.format_time

class verbose_callback():
    # Class for logging purposes only
    
    def __init__(self, _class, label):
        self._class = _class
        self.label = label
    
    def __call__(self, *args, **kwargs):
        self._class._callback(*args, **kwargs)
    
    def __repr__(self):
        return self.label

class GIF():
    blank = None
    
    cache = {}
    
    def __init__(self, url, label):
        self.callback = verbose_callback(self, "GIF callback method")
        self.video_id = url.rsplit("/", 1)[1].split("-", 1)[0]
        
        self.images = []
        GIF.blank = GIF.blank or ImageTk.PhotoImage(Image.new("RGB", (320, 180), "black"))
        
        self.var = BooleanVar()
        label.bind("<Enter>", lambda _: self.var.set(True))
        label.bind("<Leave>", lambda _: self.var.set(False))
        self.label = label
        
        if url in self.cache:
            self.images = self.cache[url]
        else:
            downloader.http(self.callback, "preview", url)
            
    def _callback(self, status_code, url, image_data=None):
        if status_code == 200:
            image = Image.open(io.BytesIO(image_data))
            self.cache[url] = self.images = [
                ImageTk.PhotoImage(image.crop((0, i*180, 320, i*180+180)))
                for i in range(10)
            ]
        else:
            self.cache[url] = self.images = [GIF.blank]*10
    
    def set(self, value):
        if self.images:
            if self.var.get():
                if self.label["image"] != (str(self.images[int(value%10)]),):
                    self.label["image"] = self.images[int(value%10)]
            else:
                if self.label["image"] != (str(self.images[0]),):
                    self.label["image"] = self.images[0]
        else:
            if self.label["image"] != (str(GIF.blank),):
                self.label["image"] = GIF.blank

class Main(Layout):
    def __init__(self):
        super().__init__()
        
        self.listbox_select_callback = verbose_callback(self, "Main listbox_select_callback method")
        
        self.geometry(downloader.info.get("geometry", "1474x735+119+184"))
        def client_id(*args):
            downloader.session.headers["Client-ID"] = downloader.info["client_id"] = self.client_id_var.get()
        self.client_id_var.trace_add("write", client_id)
        self.client_id_var.set(downloader.info["client_id"])
        self.folder_var.set(downloader.info["current_folder"])
        
        self.gifs = []
        self.videos = downloader.VideoData.videos
        self.cursor, self.has_next_page = ("", ""), False
        self.chat = None
        self.save_time = time.time()
        
        if downloader.info.get("current_folder"):
            self.folder_var.set(downloader.info["current_folder"])
        
        if downloader.info.get("streamers"):
            self.box.insert(0, *sorted(downloader.info["streamers"]))
        
        for filename in sorted(os.listdir("Files")):
            self.add_section(downloader.VideoData(filename))
        
        self.instance = vlc.Instance("--verbose -1")
        self.player = self.instance.media_player_new()
        self.player.set_hwnd(self.player_frame.winfo_id())
        self.volVar.set(downloader.info["volume"])
        base_img = ImageTk.PhotoImage(Image.new("RGBA", (340, 2000), "#33393b"))
        self.chat_window.set_image(base_img)
        
        self.bind("<Left>", self.seek)
        self.bind("<Right>", self.seek)
        
        self.mainloop()
    
    def vol_change(self, *args):
        self.player.audio_set_volume(self.volVar.get())
    
    def paste(self, args):
        try:
            clip = self.clipboard_get()
        except TclError:
            pass
        else:
            if len(clip) == 30:
                self.client_id_var.set(clip)
                downloader.info.save()
    
    def add_section(self, video):
        for i, child in enumerate(self.tv.get_children()):
            if video["id"] < child:
                position = i
                break
        else:
            position = "end"
        
        t = "played" if video["played"] else ""
        self.tv.insert("", position, video["id"], text=video["id"], values=video.values, tags=t)
    
    def listbox_select(self, args):
        selection = self.box.curselection()
        
        if selection:
            children = self.video_grid.winfo_children()
            
            self.cursor, self.has_next_page = ("", ""), False
            self.gifs = []
            for child in children:
                child.destroy()
                
            downloader.http(
                self.listbox_select_callback,
                "past_broadcasts",
                (self.box.get(selection[0]), "")
            )
    
    def tick(self):
        for gif in self.gifs:
            gif.set(time.time())
        
        if not self.player:
            return
        
        video_id = self.playing.get()
        
        if not video_id:
            return
        
        video = self.videos[video_id]
        
        if self.player.is_playing():
            self.chat(video["played"])
            
            video["played"] = self.player.get_time() / 1000
            if time.time() > self.save_time + 1:
                video.save()
                self.save_time = time.time()
            self.tv.item(video_id, values=video.values)
            
            player_length = format_time(self.player.get_length() / 1000)
            if self.press:
                length = f"{format_time(self.scale.get() / 1000)} / {player_length}"
            else:
                self.scaleVar.set(video["played"] * 1000)
                length = f"{format_time(video['played'])} / {player_length}"
            self.elapsedVar.set(length)
        
        if self.player.get_position() == 1:
            # Video sometimes ends at less than 1, need to find a fix.
            self.next()
    
    def add_download(self, item):
        if item["id"] not in self.videos:
            downloader.http(self.add_callback, "video", tuple(item.items()))
        
    def add_callback(self, video):
        self.add_section(video)
        
    def _callback(self, data):
        if data == "Valid Client ID required":
            self.log_var.set(data)
            self.notebook.select(3)
            return
        
        user = data.json()[0]["data"]["user"]
        
        if user is None:
            return ttk.Label(self.video_grid, text="User not found.").grid()
        
        first = user["videos"]["edges"][0]
        self.cursor = first["node"]["owner"]["login"], first["cursor"]
        self.has_next_page = user["videos"]["pageInfo"]["hasNextPage"]
        
        max_width = (self.winfo_width() - 134 - 321 - 5) // 320
        
        tv_children = set(self.tv.get_children())
        current_grid_count = len(self.video_grid.winfo_children())
        
        try:
            for n, item in enumerate(user["videos"]["edges"], current_grid_count):
                item = {
                    "animatedPreviewURL": item["node"]["animatedPreviewURL"],
                                  "game": item["node"]["game"]["displayName"],
                                    "id": item["node"]["id"],
                                "length": item["node"]["lengthSeconds"],
                           "publishedAt": item["node"]["publishedAt"],
                                 "title": item["node"]["title"]
                }
                
                selection = self.box.curselection()
                if selection and self.box.get(selection[0]) != self.cursor[0]:
                    break
                
                frame = ttk.Frame(self.video_grid)
                frame.grid(column=n%max_width, row=n//max_width)
                
                preview_label = ttk.Label(frame)
                preview_label.grid(columnspan=2)
                
                title_lbl = ttk.Label(frame, text=item["title"], wraplength=320)
                title_lbl.grid(column=0, columnspan=2, sticky="w")
                
                length_lbl = ttk.Label(frame, text=format_time(item["length"]))
                length_lbl.grid(column=0, row=2, sticky="w")
                
                state = ("normal", "disabled")[item["id"] in tv_children]
                download_btn = ttk.Button(frame, text="Download", state=state)
                def d(item=item, btn=download_btn):
                    self.add_download(item)
                    btn["state"] = "disabled"
                download_btn.configure(command=d)
                download_btn.grid(column=1, row=2, sticky="e")
                self.download_btns[item["id"]] = download_btn
                
                game_lbl = ttk.Label(frame, text=item["game"])
                game_lbl.grid(column=0, columnspan=2, row=3, sticky="w")
                
                publishedAt = datetime.strptime(item["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")
                ttk.Label(frame, text=publishedAt.ctime()).grid(column=0, sticky="w")
                
                self.gifs.append(GIF(item["animatedPreviewURL"], preview_label))
        except TclError:
            pass
    
    def download(self, video_id=None):
        if self.download_btn["text"] == "Stop Download":
            self.downloading.set("")
            self.download_btn["text"] = "Download"
            return
        
        video_id = video_id or self.tv.selection()[0]
        self.downloading.set(video_id)
        self.download_btn["text"] = "Stop Download"
        
        downloader.download(
            self.download_callback,
            self.videos[video_id],
            self.speed_var,
            self.downloading
        )
    
    def download_callback(self, video, x=None):
        title, streamer, downloaded, played = video.values
        
        if isinstance(x, int):
            title, streamer, downloaded, played = title, streamer, f"Chat: {x}", played
        
        self.tv.item(video["id"], values=(title, streamer, downloaded, played))
        
        if x is None:
            self.downloading.set("")
            
            if self.tv.selection() == (video["id"],):
                self.btn_state("finished_download")
        
        if video["downloaded"] == len(video["vod_parts"]):
            for item in self.tv.get_children():
                if self.tv.item(item, "values")[2] != "100.00%":
                    self.download(item)
                    break
    
    def select(self, filedialog):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)
            downloader.info["current_folder"] = folder
    
    def delete(self):
        selection, = self.tv.selection()
        
        if self.downloading.get() == selection:
            self.downloading.set("")
        
        if self.playing.get() == selection:
            self.playing.set("")
        
        self.tv.delete(selection)
        self.videos[selection].delete()
        
        self.btn_state("delete")
        if selection in self.download_btns:
            self.download_btns[selection]["state"] = "normal"
    
    def load(self, iid=None):
        selection = iid or self.tv.selection()[0]
        
        video = self.videos[selection]
        self.title(f"{video['user_name']} - {video['title']}")
        filename = f"{downloader.info['files'][selection]}/Files/{video['id']}/video.mp4"
        self.playing.set(selection)
        self.player.set_media(self.instance.media_new(filename))
        
        self.scale.configure(to_=int(video["total_duration"] * 1000))
        self.play()
        self.tv.item(selection, tags="played")
        self.chat = Chat(video, self.chat_window)
        
        # resume
        if video["played"] > 0:
            self.player.set_time(int(video["played"] * 1000))
            self.chat.seek(video["played"])
        
        self.notebook.select(0)
    
    def play(self):
        if self.playing.get():
            if self.player.is_playing():
                self.play_btn.play()
                self.player.pause()
            else:
                self.play_btn.pause()
                self.player.play()
    
    def stop(self):
        if self.player:
            
            self.player.stop()
            self.play_btn.play()
            if self.chat:
                self.chat.seek(0)
            
            video = self.videos[self.playing.get()]
            video["played"] = 0
            self.tv.item(video["id"], values=video.values, tags="")
            self.elapsedVar.set("00:00:00 / 00:00:00")
            self.scaleVar.set(0)
            self.title("Twitch Player")
    
    def next(self):
        playing = self.playing.get()
        
        if playing:
            self.stop()
            
            next_iid = self.tv.next(playing)
            if self.tv.item(next_iid, "values")[1] == "100.00%":
                self.load(next_iid)
                
    def load_next_page(self):
        selection = self.box.curselection()
        
        if self.has_next_page:
            self.has_next_page = False
            values = (self.box.get(selection[0]), self.cursor[1]) if selection else self.cursor
            downloader.http(self.listbox_select_callback, "past_broadcasts", values)
    
    def tv_select(self, _):
        video = self.videos[self.tv.selection()[0]]
        
        if self.downloading.get() == video["id"]:
            self.btn_state("downloading")
        elif video["downloaded"] < len(video["vod_parts"]):
            self.btn_state("pending_download")
        else:
            self.btn_state("finished_download")
    
    def btn_state(self, state):
        self.download_btn["text"] = ("Download", "Stop Download")[state == "downloading"]
        self.download_btn["state"] = ("disabled", "normal")[state in ("downloading", "pending_download")]
        self.load_btn["state"] = ("disabled", "normal")[state == "finished_download"]
        self.delete_btn["state"] = ("normal", "disabled")[state == "delete"]
    
    def seek(self, key):
        values = {"Left": -10, "Right": 10}
        
        if key.keysym not in values:
            return
            
        delta = values[key.keysym]
        
        if self.player.is_playing() and self.notebook.select() == ".!frame":
            current_time = self.player.get_time()
        
            self.player.set_time(current_time + delta * 1000)
            self.chat.seek(current_time / 1000 + delta)
    
    def pressed(self, args):
        self.press = True
        if self.scale.identify(args.x, args.y) in ("trough1", "trough2", "trough"):
            ratio = self.scale.cget("to") / (self.scale.winfo_width() - 30)
            self.scaleVar.set((args.x - 15) * ratio)
    
    def unpressed(self, args):
        self.press = False
        if self.scale.identify(args.x, args.y) and self.player:
            current_time = self.scale.get()
            self.player.set_time(int(current_time))
            if self.chat:
                self.chat.seek(current_time / 1000)
            
    def end(self):
        downloader.info["geometry"] = self.old_geometry or self.geometry()
        downloader.info["streamers"] = self.box.get(0, "end")
        downloader.info["volume"] = self.volVar.get()
        downloader.info.save()
        
        for video in self.videos.values():
            video.save()
        
        self.destroy()

if __name__ == "__main__":
    Main()