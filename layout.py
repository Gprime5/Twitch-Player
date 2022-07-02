import ctypes
import ctypes.wintypes
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.ttk as ttk

class Chat_window(tk.Label):
    def set_image(self, img):
        """Separating the assignments causes the chat to only show every 2nd frame.
        I don't know why.
        
        All 3 assignments here have the same problem
        
        self.chat_window["image"] = ImageTk.PhotoImage(self.draw(self.queue.get()))
        self.chat_window.image = self.chat_window["image"]
        
        self.chat_window.image = ImageTk.PhotoImage(self.draw(self.queue.get()))
        self.chat_window["image"] = self.chat_window.image
        
        self.chat_window.image = self.chat_window["image"] = ImageTk.PhotoImage(self.draw(self.queue.get()))
        
        """
        
        # The canvas image must be assigned like this.
        self["image"] = self.image = img

class Layout(tk.Tk):
    def __init__(self):
        super().__init__()
        
        try:
            # Load theme
            self.tk.call('lappend', 'auto_path', 'awthemes-10.4.0')
            self.tk.call('package', 'require', 'awdark')
        except tk.TclError:
            pass
        else:
            ttk.Style().theme_use("awdark")
        
        # Hidden window to keep taskbar icon visible when fullscreen
        self.toplevel = tk.Toplevel(self)
        self.toplevel.title("Twitch Player")
        self.toplevel.attributes("-alpha", 0)
        self.toplevel.overrideredirect(True)
        self.toplevel.bind("<Map>", lambda args: self.deiconify())
        self.toplevel.bind("<Unmap>", lambda args: self.withdraw())
        self.toplevel.bind("<Configure>", lambda args: self.lift() and self.focus_force())
        self.toplevel.img = tk.PhotoImage(file="icon.png")
        tk.Label(self.toplevel, image=self.toplevel.img).pack()
        
        self.title("Twitch Player")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        self.bind("<Escape>", lambda args: self.end())
        self.bind("<Double-Button-1>", self.fullscreen)
        self.download_btns = {}
        self.downloading = tk.StringVar()
        self.old_geometry = None
        self.playing = tk.StringVar()
        
        self.notebook = notebook = ttk.Notebook(self)
        notebook.grid(sticky="nwes")
        notebook.add(self.player_page(), text="Player")
        notebook.add(self.browse_page(), text="Browse")
        notebook.add(self.download_page(), text="Download")
        notebook.add(self.settings_page(), text="Settings")
        
        self.chat_window = Chat_window(self, bg="#33393b", highlightbackground="black", anchor="s")
        self.chat_window.grid(column=1, row=0, sticky="nes")

        self.after(10, self._tick)
        
        self.protocol("WM_DELETE_WINDOW", self.end)
    
    def fullscreen(self, args):
        self.toplevel.overrideredirect(bool(self.old_geometry))
        
        if self.old_geometry:
            self.geometry(self.old_geometry)
            self.old_geometry = None
        else:
            for t, r, b, l in get_monitors():
                if l < args.x_root <= r and t < args.y_root <= b:
                    self.old_geometry = self.geometry()
                    self.geometry(f"{r-l}x{b-t}+{l}+{t}")
                    break
        
        self.overrideredirect(bool(self.old_geometry))
    
    def player_page(self):
        frame = ttk.Frame(self)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        
        self.player_frame = ttk.Frame(frame)
        self.player_frame.grid(columnspan=3, sticky="nwes")
        
        self.elapsedVar = tk.StringVar()
        self.elapsedVar.set("00:00:00 / 00:00:00")
        ttk.Label(frame, textvariable=self.elapsedVar).grid(column=0, row=1)
        
        self.scaleVar = tk.DoubleVar()
        # Using tk.Scale instead of ttk.Scale
        # tk.Scale allows the functionality of clicking on the trough 
        # then the slider will remain dragged while holding down the mouse.
        # ttk.Scale doesn't allow this functionality.
        self.scale = tk.Scale(frame, orient="horizontal", variable=self.scaleVar, bg="black", showvalue=False, troughcolor="#33393B", activebackground="black", highlightbackground="black", bd=0, sliderrelief="flat", sliderlength="25")
        self.scale.grid(column=0, row=2, columnspan=3, sticky="we")
        self.scale.bind("<Button-1>", self.pressed)
        self.scale.bind("<ButtonRelease-1>", self.unpressed)
        self.press = False
        
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(column=0, row=3)
        
        stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop)
        stop_btn.grid(column=0, row=0, padx=5, pady=5)
        
        self.play_btn = ttk.Button(btn_frame, text="Play", command=self.play, width=10)
        self.play_btn.grid(column=1, row=0, padx=5, pady=5)
        self.play_btn.play = lambda: self.play_btn.__setitem__("text", "Play")
        self.play_btn.stop = lambda: self.play_btn.__setitem__("text", "Stop")
        self.play_btn.pause = lambda: self.play_btn.__setitem__("text", "Pause")
        
        next_btn = ttk.Button(btn_frame, text="Next", command=self.next)
        next_btn.grid(column=2, row=0, padx=5, pady=5)
        
        ttk.Label(frame, text="Volume ").grid(column=1, row=3)
        self.volVar = tk.IntVar()
        self.volVar.trace_add("write", self.vol_change)
        vol = ttk.Scale(frame, variable=self.volVar, from_=0, to_=100, length=100)
        vol.grid(column=2, row=3)

        return frame
    
    def vol_change(self, *args):
        print(self.volVar.get())
    
    def next(self):
        print("next")
    
    def browse_page(self):
        frame = ttk.Frame(self)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        
        self.box = tk.Listbox(frame)
        self.box.grid(sticky="nwse")
        self.box.bind("<<ListboxSelect>>", self.listbox_select)
        
        self.streamer_var = tk.StringVar()
        self.streamer_var.set("Enter to add streamer")
        entry = ttk.Entry(frame, textvariable=self.streamer_var)
        entry.grid(column=0, row=1)
        entry.bind("<FocusIn>", lambda args: self.streamer_var.set(""))
        entry.bind("<FocusOut>", lambda args: self.streamer_var.set("Enter to add streamer"))
        
        def add_streamer(args):
            if self.streamer_var.get() != "":
                if self.streamer_var.get() not in self.box.get(0, "end"):
                    self.box.insert("end", self.streamer_var.get())
        entry.bind("<Return>", add_streamer)
    
        def delete_streamer():
            selection = self.box.curselection()
            if selection:
                self.box.delete(selection[0])
        remove_btn = ttk.Button(frame, text="Remove", command=delete_streamer)
        remove_btn.grid(column=0, row=2, sticky="nwes")
        
        video_frame = ttk.Frame(frame)
        video_frame.grid(column=1, row=0, rowspan=3, sticky="nwes")
        video_frame.columnconfigure(0, weight=1)
        video_frame.rowconfigure(0, weight=1)
        
        yscr = lambda f, l: scroll(ys, f, l) or l == "1.0" and self.load_next_page()
        canvas = tk.Canvas(video_frame, bg="#33393B", highlightthickness=0, yscrollcommand=yscr)
        canvas.grid(sticky="nwes", padx=0, pady=0)
        
        def _on_mousewheel(event):
            if canvas.yview()[0] > 0 or event.delta < 0:
                canvas.yview_scroll(int(-event.delta/120), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        self.video_grid = ttk.Frame(canvas)
        self.video_grid.grid(sticky="nwes", padx=0, pady=5)
        canvas.create_window((0, 0), window=self.video_grid, anchor="nw")
        
        scrollregion = lambda args: canvas.configure(scrollregion=canvas.bbox("all"))
        self.video_grid.bind("<Configure>", scrollregion)
        
        ys = ttk.Scrollbar(video_frame, orient="vertical", command=canvas.yview)
        ys.grid(column=1, row=0, sticky="ns")
        
        return frame
    
    def load_next_page(self):
        print("load_next_page")
    
    def download_page(self):
        frame = ttk.Frame(self)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        
        self.download_btn = ttk.Button(frame, text="Download", command=self.download, state="disabled")
        self.download_btn.grid(padx=5, pady=5, sticky="e")
        
        self.load_btn = ttk.Button(frame, text="Load", command=self.load, state="disabled")
        self.load_btn.grid(column=1, row=0, padx=5, pady=5, sticky="e")
        
        self.delete_btn = ttk.Button(frame, text="Delete", command=self.delete, state="disabled")
        self.delete_btn.grid(column=1, row=2, padx=5, pady=5, sticky="e")
        
        self.tv = Tree(frame)
        self.tv["selectmode"] = "browse"
        self.tv.bind('<<TreeviewSelect>>', self.tv_select)
        self.tv.tag_configure("played", background="grey40")
        self.tv.grid(column=0, row=1, columnspan=2, sticky="nwes")
        
        return frame
    
    def settings_page(self):
        frame = ttk.Frame(self)
        
        def validate(value_if_allowed, text):
            return text in '0123456789'
        
        self.log_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.log_var).grid(column=0, row=0, padx=5, pady=5, sticky="e", columnspan=2)
        
        lbl = ttk.Label(frame, text="Client ID (click to paste): ")
        lbl.grid(column=0, row=1, padx=5, pady=5, sticky="e")
        self.client_id_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.client_id_var, state="disabled", width=50, show="*")
        entry.grid(column=1, row=1, padx=5, pady=5, sticky="w")
        entry.bind("<ButtonRelease-1>", self.paste)
        
        self.speed_var = tk.IntVar()
        self.speed_var.set(12000)
        lbl = ttk.Label(frame, text="Download Speed: ")
        lbl.grid(column=0, row=2, padx=5, pady=5, sticky="e")
        vcmd = (self.register(validate), '%P', '%S')
        spinbox = ttk.Spinbox(
            frame, from_=0, to_=2**20,
            textvariable=self.speed_var,
            validate="key",
            validatecommand=vcmd,
            width=50
        )
        spinbox.grid(column=1, row=2, padx=5, pady=5, sticky="w")
        
        btn = ttk.Button(frame, text="Select File", command=lambda: self.select(fd))
        btn.grid(column=0, row=3, padx=5, pady=5)
        
        self.folder_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.folder_var, state="disabled", width=50)
        entry.grid(column=1, row=3, padx=5, pady=5, sticky="w")
        
        return frame
        
    def paste(self, args):
        print("paste")
    
    def select(self, args):
        print("select")
    
    def download(self):
        print("download")
    
    def load(self):
        print("load")
    
    def delete(self):
        print("delete")
    
    def tv_select(self):
        print("tv_select")
    
    def listbox_select(self, args):
        print("listbox select")
        
    def tick(self):
        pass
        
    def _tick(self):
        self.tick()
        self.after(10, self._tick)
    
    def pressed(self, args):
        print("pressed")
    
    def unpressed(self, args):
        print("unpressed")
    
    def play(self):
        print("play")
    
    def stop(self):
        print("stop")
    
    def end(self):
        self.destroy()

def get_monitors():
    """
    This function returns the bounding box of all monitors.
    Tkinter's default fullscreen function will only fullscreen on the primary monitor.
    The purpose of having this function is to be able to fullscreen on a secondary monitor.
    
    The workaround is to check which monitor the mouse is in
    when the fullscreen function is called,
    then set the geometry to match the monitor that the mouse is in.
    """
    
    monitors = []
    
    def callback(a, b, rect, d):
        # a, b and d are unused
        rct = rect.contents
        monitors.append((rct.top, rct.right, rct.bottom, rct.left))
        
        return 1
        
    ctypes.windll.user32.EnumDisplayMonitors(
        0, None,
        ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.wintypes.RECT),
            ctypes.c_double,
        )(callback),
        0
    )
    
    return monitors

class Tree(ttk.Treeview):
    def __init__(self, parent):
        self.frame = ttk.Frame(parent)
        
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)
        
        self.parent = parent
        
        super().__init__(
            self.frame,
            xscroll=lambda f, l: scroll(xs, f, l),
            yscroll=lambda f, l: scroll(ys, f, l)
        )
        super().grid(sticky="nwes")
        
        xs = ttk.Scrollbar(self.frame, orient="horizontal", command=self.xview)
        xs.grid(column=0, row=1, sticky="we")
        
        ys = ttk.Scrollbar(self.frame, orient="vertical", command=self.yview)
        ys.grid(column=1, row=0, sticky="ns")
        
        columns = [
            ("ID", 100),
            ("Streamer", 100),
            ("Title", 400),
            ("Downloaded", 80),
            ("Played", 30)
        ]
        
        self["columns"] = [n[0] for n in columns[1:]]
        self.heading("#0", text=columns[0][0], anchor="w")
        self.column("#0", stretch=0, anchor="w", minwidth=columns[0][1], width=columns[0][1])
        
        for header, width in columns[1:-1]:
            self.heading(header, text=header, anchor="w")
            self.column(header, stretch=0, anchor="w", minwidth=width, width=width)
            
        header = columns[-1][0]
        self.heading(header, text=header, anchor="w")
        self.column(header, stretch=1, anchor="w", minwidth=columns[-1][1], width=columns[-1][1])
    
    def grid(self, *args, **kwargs):
        self.frame.grid(*args, **kwargs)
        
        if "row" in kwargs:
            self.parent.rowconfigure(kwargs["row"], weight=1)
        
def scroll(sbar, first, last):
    first, last = float(first), float(last)
    if first <= 0 and last >= 1:
        sbar.grid_remove()
    else:
        sbar.grid()
    sbar.set(first, last)

if __name__ == "__main__":
    Layout().mainloop()