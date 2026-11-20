"""FileHub VN - A local, offline file manager for Windows.

No telemetry, network activity, or automatic file deletion.
Python 3.10+; packaged for Windows with PyInstaller.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Menu, StringVar, BooleanVar, Entry, Text,
    messagebox, simpledialog, filedialog, TclError,
)
from tkinter import ttk

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None

APP_NAME = "FileHub VN"
DISPLAY_LIMIT = 10000
BATCH_SIZE = 240
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

LIGHT = {
    "bg": "#F3F6FB", "panel": "#FFFFFF", "text": "#172238",
    "muted": "#718096", "line": "#DCE4EF", "accent": "#2563EB",
    "soft": "#EAF1FF", "danger": "#C62838", "selection": "#DCE9FF",
    "alternate": "#F8FAFD", "input": "#F8FAFD",
}
DARK = {
    "bg": "#121824", "panel": "#1D2737", "text": "#F1F5FA",
    "muted": "#9DADC4", "line": "#354256", "accent": "#78A7FF",
    "soft": "#253B5D", "danger": "#FF8C95", "selection": "#324C73",
    "alternate": "#243144", "input": "#263348",
}


def config_file() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "FileHubVN" / "settings.json"


def valid_new_name(name: str) -> bool:
    if not name or name.strip() != name or name in {".", ".."}:
        return False
    if any(c in name for c in '/\\\0'):
        return False
    if os.name == "nt":
        if any(c in name for c in '<>:"|?*') or name.endswith((" ", ".")):
            return False
        if name.split(".", 1)[0].upper() in WINDOWS_RESERVED:
            return False
    return True


def is_within(path: str | Path, parent: str | Path) -> bool:
    """True if path == parent or is under parent; works for different drives."""
    p = os.path.normcase(os.path.realpath(str(path)))
    q = os.path.normcase(os.path.realpath(str(parent)))
    try:
        return os.path.commonpath((p, q)) == q
    except ValueError:
        return False


def collision_free_path(dst: Path) -> Path:
    """Auto-name a copy rather than overwriting an existing file/folder."""
    if not dst.exists() and not dst.is_symlink():
        return dst
    stem = dst.stem if dst.is_file() else dst.name
    ext = dst.suffix if dst.is_file() else ""
    for n in range(1, 10001):
        suffix = " - bản sao" if n == 1 else f" - bản sao ({n})"
        candidate = dst.with_name(f"{stem}{suffix}{ext}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise OSError("Không thể tìm tên file trống tại thư mục đích.")


def collapse_nested(paths: list[str]) -> list[str]:
    """Avoid moving a child twice when both parent and child are selected."""
    distinct = list(dict.fromkeys(os.path.normpath(p) for p in paths))
    return [p for p in distinct if not any(p != q and is_within(p, q) for q in distinct)]


def file_size(num: int | None) -> str:
    if num is None:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "—"


def timestamp_string(stamp: float) -> str:
    try:
        return datetime.fromtimestamp(stamp).strftime("%d/%m/%Y %H:%M")
    except (OSError, OverflowError, ValueError):
        return "—"


def known_folders() -> list[tuple[str, Path]]:
    home = Path.home()
    onedrive = Path(os.environ.get("OneDrive", "")) if os.environ.get("OneDrive") else None
    def pick(name: str) -> Path:
        choices = [home / name]
        if onedrive:
            choices.append(onedrive / name)
        choices.append(home / "OneDrive" / name)
        return next((x for x in choices if x.is_dir()), choices[0])
    return [("Màn hình Desktop", pick("Desktop")), ("Tài liệu", pick("Documents")),
            ("Tải xuống", pick("Downloads")), ("Hình ảnh", pick("Pictures")),
            ("Video", pick("Videos")), ("Thư mục người dùng", home)]


def windows_drives() -> list[str]:
    if os.name != "nt":
        return ["/"]
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return [f"{chr(ord('A') + i)}:\\" for i in range(26) if mask & (1 << i)]
    except Exception:
        return ["C:\\"]


def open_in_system(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


@dataclass
class FileItem:
    path: str
    name: str
    is_dir: bool
    size: int | None
    modified: float
    parent: str

    @property
    def kind(self) -> str:
        if self.is_dir:
            return "Thư mục"
        ext = Path(self.name).suffix
        return f"Tệp {ext.upper()}" if ext else "Tệp tin"


class FileHub(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("FileHub VN | Quản lý tệp và thư mục")
        try:
            bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            icon = bundle_root / "assets" / "filehub.ico"
            if icon.exists():
                self.iconbitmap(default=str(icon))
        except (TclError, OSError):
            pass
        self.geometry("1320x780")
        self.minsize(930, 560)
        self.settings = self.read_settings()
        self.dark_mode = BooleanVar(value=bool(self.settings.get("dark_mode", False)))
        self.show_hidden = BooleanVar(value=bool(self.settings.get("show_hidden", False)))
        self.search_subfolders = BooleanVar(value=False)
        self.show_details = BooleanVar(value=True)
        self.search_query = StringVar()
        self.address = StringVar()
        self.status = StringVar(value="Sẵn sàng")
        self.summary = StringVar(value="")
        self.detail_name = StringVar(value="Chọn một file hoặc thư mục")
        self.detail_type = StringVar(value="")
        self.detail_size = StringVar(value="")
        self.detail_date = StringVar(value="")
        self.detail_path = StringVar(value="")
        self.favorites = [p for p in self.settings.get("favorites", []) if isinstance(p, str) and os.path.isdir(p)]
        self.recents = [p for p in self.settings.get("recents", []) if isinstance(p, str) and os.path.isdir(p)]
        desktop = known_folders()[0][1]
        self.current_path = str(desktop if desktop.is_dir() else Path.home())
        self.history: list[str] = []
        self.history_index = -1
        self.items: dict[str, FileItem] = {}
        self.search_after: str | None = None
        self.current_generation = 0
        self.scan_stop = threading.Event()
        self.events: queue.Queue = queue.Queue()
        self.clipboard_paths: list[str] = []
        self.clipboard_mode = "copy"
        self.running_op = False
        self.sort_column = "name"
        self.sort_reverse = False
        self.sidebar_targets: dict[str, str] = {}
        self.search_query.trace_add("write", self._schedule_search)
        self._build_ui()
        self.navigate(self.current_path)
        self.after(120, self._handle_events)
        self.bind("<Control-c>", self.on_copy)
        self.bind("<Control-x>", self.on_cut)
        self.bind("<Control-v>", self.on_paste)
        self.bind("<Control-a>", self.select_all)
        self.bind("<F2>", self.on_rename)
        self.bind("<F5>", lambda e: self.refresh())
        self.bind("<Delete>", self.on_delete)
        self.bind("<Alt-Left>", lambda e: self.go_back())
        self.bind("<Alt-Right>", lambda e: self.go_forward())
        self.bind("<Alt-Up>", lambda e: self.go_up())
        self.bind("<Control-f>", self._focus_search)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    @staticmethod
    def read_settings() -> dict:
        try:
            data = json.loads(config_file().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self) -> None:
        path = config_file()
        data = {
            "dark_mode": self.dark_mode.get(), "show_hidden": self.show_hidden.get(),
            "favorites": self.favorites, "recents": self.recents[:12],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def palette(self) -> dict[str, str]:
        return DARK if self.dark_mode.get() else LIGHT

    def _button(self, parent, label, command, style="Tool.TButton", width=None):
        kw = {"style": style, "command": command}
        if width:
            kw["width"] = width
        return ttk.Button(parent, text=label, **kw)

    def _build_ui(self) -> None:
        p = self.palette()
        self.configure(bg=p["bg"])
        self._setup_styles()
        for child in self.winfo_children():
            child.destroy()
        self.main_frame = Frame(self, bg=p["bg"])
        self.main_frame.pack(fill="both", expand=True, padx=15, pady=13)

        header = Frame(self.main_frame, bg=p["panel"], highlightthickness=1, highlightbackground=p["line"])
        header.pack(fill="x", pady=(0, 11))
        top = Frame(header, bg=p["panel"])
        top.pack(fill="x", padx=18, pady=(13, 11))
        Label(top, text="▣", bg=p["panel"], fg=p["accent"], font=("Segoe UI", 25, "bold")).pack(side="left")
        brand = Frame(top, bg=p["panel"])
        brand.pack(side="left", padx=(10, 20))
        Label(brand, text="FileHub VN", bg=p["panel"], fg=p["text"], font=("Segoe UI", 17, "bold")).pack(anchor="w")
        Label(brand, text="Quản lý tệp tin trên máy tính • Hoạt động ngoại tuyến", bg=p["panel"], fg=p["muted"], font=("Segoe UI", 9)).pack(anchor="w")
        self._button(top, "◐  Giao diện", self.toggle_theme).pack(side="right", padx=(8, 0))
        self._button(top, "☷  Chi tiết", self.toggle_details).pack(side="right", padx=(8, 0))
        self._button(top, "↻  Làm mới", self.refresh).pack(side="right")

        nav = Frame(header, bg=p["panel"])
        nav.pack(fill="x", padx=17, pady=(0, 12))
        self.back_btn = self._button(nav, "‹", self.go_back, width=3)
        self.back_btn.pack(side="left", padx=(0, 4))
        self.forward_btn = self._button(nav, "›", self.go_forward, width=3)
        self.forward_btn.pack(side="left", padx=(0, 4))
        self._button(nav, "↑", self.go_up, width=3).pack(side="left", padx=(0, 9))
        self.address_entry = ttk.Entry(nav, textvariable=self.address, style="Path.TEntry", font=("Segoe UI", 10))
        self.address_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 9))
        self.address_entry.bind("<Return>", self.on_address)
        self._button(nav, "Đến", self.on_address, style="Primary.TButton").pack(side="left", padx=(0, 16))
        search_frame = Frame(nav, bg=p["panel"])
        search_frame.pack(side="right")
        Label(search_frame, text="⌕  Tìm:", font=("Segoe UI", 10), bg=p["panel"], fg=p["muted"]).pack(side="left")
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_query, style="Path.TEntry", width=26, font=("Segoe UI", 10))
        self.search_entry.pack(side="left", ipady=6, padx=(4, 0))
        self.search_entry.bind("<Escape>", lambda e: self.search_query.set(""))

        content = Frame(self.main_frame, bg=p["bg"])
        content.pack(fill="both", expand=True)
        self.sidebar_box = Frame(content, width=229, bg=p["panel"], highlightthickness=1, highlightbackground=p["line"])
        self.sidebar_box.pack(side="left", fill="y", padx=(0, 11))
        self.sidebar_box.pack_propagate(False)
        Label(self.sidebar_box, text="TRUY CẬP NHANH", bg=p["panel"], fg=p["muted"], font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=15, pady=(17, 10))
        self.sidebar = ttk.Treeview(self.sidebar_box, show="tree", selectmode="browse", style="Nav.Treeview")
        self.sidebar.pack(fill="both", expand=True, padx=8, pady=(0, 7))
        self.sidebar.bind("<<TreeviewSelect>>", self._sidebar_click)
        self._sidebar_rebuild()
        sidebottom = Frame(self.sidebar_box, bg=p["panel"])
        sidebottom.pack(fill="x", padx=8, pady=(5, 13))
        self._button(sidebottom, "+  Thêm yêu thích", self.on_add_favorite).pack(fill="x")

        self.center = Frame(content, bg=p["panel"], highlightthickness=1, highlightbackground=p["line"])
        self.center.pack(side="left", fill="both", expand=True)
        action_box = Frame(self.center, bg=p["panel"])
        action_box.pack(fill="x", padx=14, pady=(14, 9))
        title_area = Frame(action_box, bg=p["panel"])
        title_area.pack(side="left", fill="x", expand=True)
        self.folder_title = Label(title_area, text="Danh sách tệp và thư mục", font=("Segoe UI", 12, "bold"), fg=p["text"], bg=p["panel"], anchor="w")
        self.folder_title.pack(anchor="w")
        Label(title_area, textvariable=self.summary, fg=p["muted"], bg=p["panel"], font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        self._button(action_box, "+  Thư mục mới", self.on_new_folder, "Primary.TButton").pack(side="right", padx=(6, 0))
        self._button(action_box, "Mở vị trí...", self.choose_folder).pack(side="right")

        toolbar = Frame(self.center, bg=p["panel"])
        toolbar.pack(fill="x", padx=13, pady=(0, 8))
        actions = [
            ("Mở", self.open_selection), ("Sao chép", self.on_copy), ("Cắt", self.on_cut),
            ("Dán", self.on_paste), ("Đổi tên", self.on_rename), ("Xóa", self.on_delete),
        ]
        for i, (name, callback) in enumerate(actions):
            self._button(toolbar, name, callback, style="Danger.TButton" if name == "Xóa" else "Tool.TButton").pack(side="left", padx=(0, 5))
        search_options = Frame(self.center, bg=p["panel"])
        search_options.pack(fill="x", padx=14, pady=(0, 7))
        ttk.Checkbutton(search_options, text="Tìm cả thư mục con", variable=self.search_subfolders,
                        command=self.refresh, style="App.TCheckbutton").pack(side="left", padx=(0, 15))
        ttk.Checkbutton(search_options, text="Hiển thị tệp ẩn", variable=self.show_hidden,
                        command=self._toggle_hidden, style="App.TCheckbutton").pack(side="left")

        table_area = Frame(self.center, bg=p["panel"])
        table_area.pack(fill="both", expand=True, padx=(12, 10), pady=(0, 8))
        self.table = ttk.Treeview(table_area, columns=("name", "type", "size", "mtime", "location"),
                                  show="headings", selectmode="extended", style="Files.Treeview")
        for key, title, width, anchor in [
            ("name", "Tên file / thư mục", 240, "w"), ("type", "Loại", 110, "w"),
            ("size", "Kích thước", 95, "e"), ("mtime", "Cập nhật", 140, "w"),
            ("location", "Thư mục chứa", 155, "w"),
        ]:
            self.table.heading(key, text=title, command=lambda k=key: self.sort_by(k))
            self.table.column(key, width=width, minwidth=70, anchor=anchor, stretch=key in ("name", "location"))
        scroll_y = ttk.Scrollbar(table_area, orient="vertical", command=self.table.yview)
        scroll_x = ttk.Scrollbar(table_area, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table_area.rowconfigure(0, weight=1)
        table_area.columnconfigure(0, weight=1)
        self.table.bind("<Double-1>", self.open_selection)
        self.table.bind("<Return>", self.open_selection)
        self.table.bind("<<TreeviewSelect>>", self._selection_changed)
        self.table.bind("<Button-3>", self._context_menu)
        self.table.bind("<Button-2>", self._context_menu)
        self.table.bind("<Control-Key-f>", self._focus_search)

        self.progress = ttk.Progressbar(self.center, mode="indeterminate", style="App.Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=13, pady=(0, 8))
        self.progress.pack_forget()

        self.details_box = Frame(content, width=255, bg=p["panel"], highlightthickness=1, highlightbackground=p["line"])
        self.details_box.pack(side="right", fill="y", padx=(11, 0))
        self.details_box.pack_propagate(False)
        Label(self.details_box, text="THÔNG TIN CHI TIẾT", bg=p["panel"], fg=p["muted"],
              font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=16, pady=(19, 14))
        Label(self.details_box, text="▤", bg=p["soft"], fg=p["accent"],
              font=("Segoe UI", 38), width=5, height=2).pack(pady=(7, 15))
        Label(self.details_box, textvariable=self.detail_name, bg=p["panel"], fg=p["text"],
              wraplength=220, font=("Segoe UI", 12, "bold"), justify="center").pack(padx=13, pady=(0, 19))
        for title, variable in [("Loại", self.detail_type), ("Kích thước", self.detail_size), ("Sửa đổi lần cuối", self.detail_date), ("Đường dẫn", self.detail_path)]:
            Label(self.details_box, text=title.upper(), bg=p["panel"], fg=p["muted"],
                  font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", padx=16, pady=(0, 4))
            Label(self.details_box, textvariable=variable, bg=p["panel"], fg=p["text"],
                  font=("Segoe UI", 9), wraplength=218, justify="left", anchor="w").pack(fill="x", padx=16, pady=(0, 17))
        self._button(self.details_box, "Sao chép đường dẫn", self.copy_paths_to_os).pack(side="bottom", fill="x", padx=14, pady=(0, 14))
        if not self.show_details.get():
            self.details_box.pack_forget()
        self.center.pack_forget()
        self.center.pack(side="left", fill="both", expand=True)

        bottom = Frame(self.main_frame, bg=p["bg"])
        bottom.pack(fill="x", pady=(9, 0))
        Label(bottom, textvariable=self.status, bg=p["bg"], fg=p["muted"], anchor="w", font=("Segoe UI", 9)).pack(side="left", fill="x", expand=True)
        Label(bottom, text="Dữ liệu lưu trên máy • Xóa chuyển vào Thùng rác", bg=p["bg"], fg=p["muted"], font=("Segoe UI", 9)).pack(side="right")
        self._update_nav_buttons()

    def _setup_styles(self) -> None:
        p = self.palette()
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Tool.TButton", background=p["panel"], foreground=p["text"], bordercolor=p["line"],
                        lightcolor=p["panel"], darkcolor=p["panel"], padding=(11, 8), font=("Segoe UI", 9))
        style.map("Tool.TButton", background=[("active", p["soft"])], foreground=[("disabled", p["muted"])])
        style.configure("Primary.TButton", background=p["accent"], foreground="#FFFFFF" if not self.dark_mode.get() else "#121824",
                        bordercolor=p["accent"], padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton", background=[("active", "#1745B3" if not self.dark_mode.get() else "#A7C6FF")])
        style.configure("Danger.TButton", background=p["panel"], foreground=p["danger"],
                        bordercolor=p["line"], padding=(11, 8), font=("Segoe UI", 9))
        style.map("Danger.TButton", background=[("active", p["soft"])])
        style.configure("Path.TEntry", fieldbackground=p["input"], foreground=p["text"], bordercolor=p["line"],
                        insertcolor=p["text"], padding=4)
        style.configure("Files.Treeview", background=p["panel"], fieldbackground=p["panel"], foreground=p["text"],
                        bordercolor=p["line"], rowheight=32, font=("Segoe UI", 9))
        style.map("Files.Treeview", background=[("selected", p["selection"])], foreground=[("selected", p["text"])])
        style.configure("Files.Treeview.Heading", background=p["soft"], foreground=p["text"],
                        font=("Segoe UI", 9, "bold"), padding=(10, 10), bordercolor=p["line"])
        style.map("Files.Treeview.Heading", background=[("active", p["selection"])])
        style.configure("Nav.Treeview", background=p["panel"], fieldbackground=p["panel"], foreground=p["text"],
                        rowheight=30, borderwidth=0, font=("Segoe UI", 10))
        style.map("Nav.Treeview", background=[("selected", p["selection"])], foreground=[("selected", p["text"])])
        style.configure("App.TCheckbutton", background=p["panel"], foreground=p["text"], font=("Segoe UI", 9))
        style.map("App.TCheckbutton", background=[("active", p["panel"])])
        style.configure("App.Horizontal.TProgressbar", background=p["accent"], troughcolor=p["soft"], borderwidth=0)

    def _sidebar_rebuild(self) -> None:
        self.sidebar.delete(*self.sidebar.get_children())
        self.sidebar_targets.clear()
        groups = [
            ("THƯ MỤC", [("⌂  " + title, str(path)) for title, path in known_folders() if path.is_dir()]),
            ("YÊU THÍCH", [("★  " + Path(path).name, path) for path in self.favorites if os.path.isdir(path)]),
            ("Ổ ĐĨA", [("▣  " + root, root) for root in windows_drives()]),
            ("GẦN ĐÂY", [("◷  " + Path(path).name, path) for path in self.recents[:6] if os.path.isdir(path)]),
        ]
        for heading, rows in groups:
            if not rows:
                continue
            parent = self.sidebar.insert("", "end", text=heading, open=True)
            for name, path in rows:
                sid = self.sidebar.insert(parent, "end", text=name)
                self.sidebar_targets[sid] = path

    def _sidebar_click(self, event=None) -> None:
        selected = self.sidebar.selection()
        if not selected:
            return
        target = self.sidebar_targets.get(selected[0])
        if target and os.path.isdir(target):
            self.search_query.set("")
            self.navigate(target)

    def _update_nav_buttons(self) -> None:
        if hasattr(self, "back_btn"):
            self.back_btn.configure(state="normal" if self.history_index > 0 else "disabled")
            self.forward_btn.configure(state="normal" if self.history_index < len(self.history) - 1 else "disabled")

    def navigate(self, path: str, record=True) -> None:
        path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
        if not os.path.isdir(path):
            messagebox.showerror("Không thể truy cập", f"Thư mục không tồn tại hoặc không thể mở:\n{path}")
            return
        if record and (self.history_index < 0 or os.path.normcase(self.history[self.history_index]) != os.path.normcase(path)):
            self.history = self.history[:self.history_index + 1] + [path]
            self.history_index = len(self.history) - 1
        self.current_path = path
        self.address.set(path)
        self.folder_title.configure(text=Path(path).name or path)
        self.recents = [path] + [x for x in self.recents if os.path.normcase(x) != os.path.normcase(path)]
        self.recents = self.recents[:12]
        self.save_settings()
        self._sidebar_rebuild()
        self._update_nav_buttons()
        self.refresh()

    def go_back(self) -> None:
        if self.history_index > 0:
            self.history_index -= 1
            self.navigate(self.history[self.history_index], record=False)

    def go_forward(self) -> None:
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.navigate(self.history[self.history_index], record=False)

    def go_up(self) -> None:
        parent = str(Path(self.current_path).parent)
        if parent != self.current_path:
            self.navigate(parent)

    def on_address(self, event=None) -> None:
        value = self.address.get().strip().strip('"')
        if os.path.isfile(value):
            self.navigate(str(Path(value).parent))
        else:
            self.navigate(value)

    def choose_folder(self) -> None:
        target = filedialog.askdirectory(initialdir=self.current_path, title="Chọn thư mục cần quản lý")
        if target:
            self.search_query.set("")
            self.navigate(target)

    def _schedule_search(self, *args) -> None:
        if self.search_after:
            self.after_cancel(self.search_after)
        self.search_after = self.after(330, self.refresh)

    def _toggle_hidden(self) -> None:
        self.save_settings()
        self.refresh()

    def _hidden(self, name: str, stat_result) -> bool:
        if self.show_hidden.get():
            return False
        if name.startswith("."):
            return True
        attribs = getattr(stat_result, "st_file_attributes", 0)
        return bool(attribs & 0x2)

    def refresh(self, event=None) -> None:
        if not hasattr(self, "table"):
            return
        self.current_generation += 1
        generation = self.current_generation
        self.scan_stop.set()
        self.scan_stop = threading.Event()
        self.items.clear()
        self.table.delete(*self.table.get_children())
        self.summary.set("Đang tải dữ liệu...")
        self.status.set("Đang đọc thư mục và tìm kiếm...")
        self._selection_changed()
        folder = self.current_path
        query = self.search_query.get().strip().casefold()
        recursive = bool(query and self.search_subfolders.get())
        show_hidden = self.show_hidden.get()
        stop = self.scan_stop
        threading.Thread(target=self._scan_worker,
                         args=(generation, folder, query, recursive, show_hidden, stop), daemon=True).start()

    def _scan_worker(self, generation: int, folder: str, query: str, recursive: bool,
                     show_hidden: bool, stop: threading.Event) -> None:
        scanned = 0
        shown = 0
        errors = 0
        batch = []
        pending = [folder]
        capped = False
        while pending and not stop.is_set() and not capped:
            directory = pending.pop()
            try:
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        if stop.is_set():
                            break
                        try:
                            stat = entry.stat(follow_symlinks=False)
                            if not show_hidden and (entry.name.startswith(".") or getattr(stat, "st_file_attributes", 0) & 0x2):
                                continue
                            is_dir = entry.is_dir(follow_symlinks=False)
                            scanned += 1
                            if recursive and is_dir:
                                pending.append(entry.path)
                            if query and query not in entry.name.casefold():
                                continue
                            batch.append(FileItem(entry.path, entry.name, is_dir, None if is_dir else stat.st_size,
                                                  stat.st_mtime, directory))
                            shown += 1
                            if len(batch) >= BATCH_SIZE:
                                self.events.put(("scan_batch", generation, batch))
                                batch = []
                            if shown >= DISPLAY_LIMIT:
                                capped = True
                                break
                        except (PermissionError, OSError):
                            errors += 1
            except (PermissionError, OSError):
                errors += 1
        if batch and not stop.is_set():
            self.events.put(("scan_batch", generation, batch))
        if not stop.is_set():
            self.events.put(("scan_done", generation, shown, scanned, errors, capped))

    def _handle_events(self) -> None:
        try:
            for _ in range(32):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "scan_batch":
                    _, generation, batch = event
                    if generation == self.current_generation:
                        self._add_batch(batch)
                elif kind == "scan_done":
                    _, generation, shown, scanned, errors, capped = event
                    if generation == self.current_generation:
                        self._sort_rows()
                        msg = f"{shown:,} mục hiển thị" + (f" / {scanned:,} mục đã quét" if self.search_query.get().strip() else "")
                        self.summary.set(msg)
                        suffix = " • Đạt giới hạn 10.000 mục, thu hẹp tìm kiếm" if capped else ""
                        suffix += f" • {errors} mục không đọc được" if errors else ""
                        self.status.set(msg + suffix)
                elif kind == "op_done":
                    _, results, errors, copied, is_move = event
                    self.running_op = False
                    self.progress.stop()
                    self.progress.pack_forget()
                    if is_move and not errors:
                        self.clipboard_paths = []
                    if errors:
                        preview = "\n".join(errors[:6])
                        messagebox.showwarning("Một số thao tác không thành công", f"Đã hoàn thành {results} mục.\n\n{preview}" + (f"\n... và {len(errors)-6} lỗi khác" if len(errors)>6 else ""))
                    else:
                        self.status.set(f"Đã xử lý thành công {results} mục.")
                    self.refresh()
        except queue.Empty:
            pass
        try:
            self.after(100, self._handle_events)
        except TclError:
            pass

    def _add_batch(self, batch: list[FileItem]) -> None:
        p = self.palette()
        self.table.tag_configure("dir", foreground=p["accent"])
        self.table.tag_configure("even", background=p["alternate"])
        for item in batch:
            self.items[item.path] = item
            prefix = "▸  " if item.is_dir else "   "
            tags = ("dir",) if item.is_dir else (("even",) if len(self.items) % 2 == 0 else ())
            self.table.insert("", "end", iid=item.path,
                              values=(prefix + item.name, item.kind, file_size(item.size),
                                      timestamp_string(item.modified), item.parent if self.search_query.get() else ""), tags=tags)

    def sort_by(self, key: str) -> None:
        if self.sort_column == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = key
            self.sort_reverse = False
        self._sort_rows()

    def _sort_rows(self) -> None:
        def sort_key(item: FileItem):
            if self.sort_column == "size":
                result = item.size if item.size is not None else -1
            elif self.sort_column == "mtime":
                result = item.modified
            elif self.sort_column == "type":
                result = item.kind.casefold()
            elif self.sort_column == "location":
                result = item.parent.casefold()
            else:
                result = item.name.casefold()
            return (result, item.name.casefold())
        ordered = sorted(self.items.values(), key=sort_key, reverse=self.sort_reverse)
        # Keep directories before files even when descending.
        ordered.sort(key=lambda x: not x.is_dir)
        for index, item in enumerate(ordered):
            self.table.move(item.path, "", index)

    def selected_items(self) -> list[FileItem]:
        return [self.items[iid] for iid in self.table.selection() if iid in self.items]

    def _selection_changed(self, event=None) -> None:
        selected = self.selected_items()
        if not selected:
            self.detail_name.set("Chọn một file hoặc thư mục")
            self.detail_type.set("—")
            self.detail_size.set("—")
            self.detail_date.set("—")
            self.detail_path.set("—")
            return
        if len(selected) > 1:
            total = sum(x.size or 0 for x in selected)
            self.detail_name.set(f"Đã chọn {len(selected)} mục")
            self.detail_type.set("Nhiều mục")
            self.detail_size.set(file_size(total) + " (chỉ tính tệp)")
            self.detail_date.set("—")
            self.detail_path.set("Nhiều vị trí")
            return
        item = selected[0]
        self.detail_name.set(item.name)
        self.detail_type.set(item.kind)
        self.detail_size.set(file_size(item.size))
        self.detail_date.set(timestamp_string(item.modified))
        self.detail_path.set(item.path)

    def _context_menu(self, event) -> None:
        row = self.table.identify_row(event.y)
        if row and row not in self.table.selection():
            self.table.selection_set(row)
        p = self.palette()
        menu = Menu(self, tearoff=False, bg=p["panel"], fg=p["text"], activebackground=p["soft"], activeforeground=p["text"])
        menu.add_command(label="Mở", command=self.open_selection)
        menu.add_command(label="Mở thư mục chứa", command=self.open_containing_folder)
        menu.add_separator()
        menu.add_command(label="Sao chép", command=self.on_copy)
        menu.add_command(label="Cắt", command=self.on_cut)
        menu.add_command(label="Dán vào thư mục đang xem", command=self.on_paste)
        menu.add_command(label="Sao chép đường dẫn", command=self.copy_paths_to_os)
        menu.add_separator()
        menu.add_command(label="Đổi tên (F2)", command=self.on_rename)
        menu.add_command(label="Thêm vào yêu thích", command=self.on_add_favorite)
        menu.add_command(label="Xóa vào Thùng rác (Del)", command=self.on_delete)
        menu.add_command(label="Thông tin", command=self.properties)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def open_selection(self, event=None) -> None:
        selected = self.selected_items()
        if not selected:
            return
        item = selected[0]
        try:
            if item.is_dir:
                self.search_query.set("")
                self.navigate(item.path)
            else:
                open_in_system(item.path)
        except OSError as exc:
            messagebox.showerror("Không mở được", f"{item.path}\n\n{exc}")

    def open_containing_folder(self) -> None:
        selected = self.selected_items()
        if selected:
            self.search_query.set("")
            self.navigate(selected[0].parent)

    def on_new_folder(self, event=None) -> None:
        if self.running_op:
            return
        name = simpledialog.askstring("Tạo thư mục", "Tên thư mục mới:", initialvalue="Thư mục mới", parent=self)
        if name is None:
            return
        if not valid_new_name(name):
            messagebox.showerror("Tên không hợp lệ", "Tên không được rỗng, có dấu / hoặc \\ và các ký tự Windows bị cấm.")
            return
        path = Path(self.current_path) / name
        try:
            path.mkdir()
            self.refresh()
        except OSError as exc:
            messagebox.showerror("Không thể tạo thư mục", str(exc))

    def on_rename(self, event=None) -> None:
        if event is not None and self._focus_is_text_input():
            return None
        if self.running_op:
            return "break"
        selected = self.selected_items()
        if len(selected) != 1:
            self.status.set("Chọn đúng một mục để đổi tên.")
            return "break"
        item = selected[0]
        name = simpledialog.askstring("Đổi tên", "Tên mới:", initialvalue=item.name, parent=self)
        if name is None or name == item.name:
            return "break"
        if not valid_new_name(name):
            messagebox.showerror("Tên không hợp lệ", "Vui lòng nhập tên hợp lệ, không chứa ký tự cấm.")
            return "break"
        target = Path(item.parent) / name
        if target.exists():
            messagebox.showerror("Đã tồn tại", "Đã có tệp/thư mục trùng tên. Không ghi đè.")
            return "break"
        try:
            Path(item.path).rename(target)
            self.refresh()
        except OSError as exc:
            messagebox.showerror("Không thể đổi tên", str(exc))
        return "break"

    def _focus_is_text_input(self) -> bool:
        return self.focus_get() in (self.address_entry, self.search_entry)

    def on_copy(self, event=None) -> None:
        if event is not None and self._focus_is_text_input():
            return None
        selected = self.selected_items()
        if selected:
            self.clipboard_paths = collapse_nested([x.path for x in selected])
            self.clipboard_mode = "copy"
            self.status.set(f"Đã chọn sao chép {len(self.clipboard_paths)} mục. Chuyển tới thư mục đích và bấm Dán.")
        return "break"

    def on_cut(self, event=None) -> None:
        if event is not None and self._focus_is_text_input():
            return None
        selected = self.selected_items()
        if selected:
            self.clipboard_paths = collapse_nested([x.path for x in selected])
            self.clipboard_mode = "move"
            self.status.set(f"Đã chọn di chuyển {len(self.clipboard_paths)} mục. Chuyển tới thư mục đích và bấm Dán.")
        return "break"

    def on_paste(self, event=None) -> None:
        if event is not None and self._focus_is_text_input():
            return None
        if self.running_op:
            return "break"
        sources = self.clipboard_paths[:]
        if not sources:
            self.status.set("Chưa có file nào trong bộ nhớ sao chép của ứng dụng.")
            return "break"
        dest_dir = self.current_path
        valid = []
        rejected = []
        for source in sources:
            if not os.path.lexists(source):
                rejected.append(f"Không còn tồn tại: {source}")
            elif os.path.isdir(source) and is_within(dest_dir, source):
                rejected.append(f"Không thể dán thư mục vào chính nó: {source}")
            elif self.clipboard_mode == "move" and os.path.normcase(os.path.abspath(os.path.dirname(source))) == os.path.normcase(os.path.abspath(dest_dir)):
                rejected.append(f"Đã ở trong thư mục đích: {source}")
            else:
                valid.append(source)
        if rejected and not valid:
            messagebox.showwarning("Không thể dán", "\n".join(rejected[:5]))
            return "break"
        self._perform_background_operation(valid, dest_dir, self.clipboard_mode == "move", rejected)
        return "break"

    def _perform_background_operation(self, paths: list[str], dest_dir: str, move: bool, early_errors: list[str]) -> None:
        self.running_op = True
        self.progress.pack(fill="x", padx=13, pady=(0, 8))
        self.progress.start(12)
        self.status.set(f"Đang {'di chuyển' if move else 'sao chép'} {len(paths)} mục...")
        def worker():
            success, errors = 0, early_errors[:]
            for source in paths:
                try:
                    src = Path(source)
                    dest = collision_free_path(Path(dest_dir) / src.name)
                    if move:
                        shutil.move(str(src), str(dest))
                    elif src.is_dir():
                        shutil.copytree(src, dest, symlinks=True)
                    else:
                        shutil.copy2(src, dest)
                    success += 1
                except (OSError, shutil.Error) as exc:
                    errors.append(f"{Path(source).name}: {exc}")
            self.events.put(("op_done", success, errors, not move, move))
        threading.Thread(target=worker, daemon=True).start()

    def on_delete(self, event=None) -> None:
        if event is not None and self._focus_is_text_input():
            return None
        if self.running_op:
            return "break"
        selected = collapse_nested([x.path for x in self.selected_items()])
        if not selected:
            return "break"
        if send2trash is None:
            messagebox.showerror("Thiếu chức năng Thùng rác", "Cần cài thư viện send2trash.\nChương trình không xóa vĩnh viễn để tránh mất dữ liệu.")
            return "break"
        if not messagebox.askyesno("Chuyển vào Thùng rác", f"Chuyển {len(selected)} mục đã chọn vào Thùng rác?\n\nBạn có thể khôi phục từ Thùng rác của Windows.", icon="warning"):
            return "break"
        self.running_op = True
        self.progress.pack(fill="x", padx=13, pady=(0, 8))
        self.progress.start(12)
        def worker():
            count, errors = 0, []
            for path in selected:
                try:
                    send2trash(path)
                    count += 1
                except Exception as exc:
                    errors.append(f"{Path(path).name}: {exc}")
            self.events.put(("op_done", count, errors, False, False))
        threading.Thread(target=worker, daemon=True).start()
        return "break"

    def copy_paths_to_os(self) -> None:
        selected = self.selected_items()
        paths = [x.path for x in selected] or [self.current_path]
        self.clipboard_clear()
        self.clipboard_append("\n".join(paths))
        self.status.set(f"Đã sao chép {len(paths)} đường dẫn dưới dạng văn bản.")

    def on_add_favorite(self) -> None:
        selected = self.selected_items()
        path = selected[0].path if len(selected) == 1 and selected[0].is_dir else self.current_path
        if path not in self.favorites:
            self.favorites.append(path)
            self.save_settings()
            self._sidebar_rebuild()
            self.status.set(f"Đã thêm yêu thích: {path}")
        else:
            if messagebox.askyesno("Đã trong yêu thích", "Thư mục đã được yêu thích. Bỏ khỏi danh sách?"):
                self.favorites.remove(path)
                self.save_settings()
                self._sidebar_rebuild()

    def properties(self) -> None:
        selected = self.selected_items()
        if not selected:
            return
        item = selected[0]
        try:
            stat = os.stat(item.path)
            info = (f"Tên: {item.name}\nLoại: {item.kind}\nKích thước: {file_size(item.size)}\n"
                    f"Đường dẫn: {item.path}\nSửa đổi: {timestamp_string(stat.st_mtime)}\n"
                    f"Tạo lúc: {timestamp_string(stat.st_ctime)}")
            messagebox.showinfo("Thông tin tệp / thư mục", info)
        except OSError as exc:
            messagebox.showerror("Không xem được thông tin", str(exc))

    def _focus_search(self, event=None) -> None:
        self.search_entry.focus_set()

    def select_all(self, event=None) -> None:
        # Don't steal Ctrl+A when the user is editing an input field.
        if self.focus_get() in (self.address_entry, self.search_entry):
            return
        self.table.selection_set(self.table.get_children())
        return "break"

    def toggle_theme(self) -> None:
        self.dark_mode.set(not self.dark_mode.get())
        self.save_settings()
        self._build_ui()
        self.refresh()

    def toggle_details(self) -> None:
        self.show_details.set(not self.show_details.get())
        if self.show_details.get():
            self.details_box.pack(side="right", fill="y", padx=(11, 0))
            self.center.pack_forget()
            self.center.pack(side="left", fill="both", expand=True)
        else:
            self.details_box.pack_forget()

    def on_close(self) -> None:
        if self.running_op:
            messagebox.showwarning("Đang xử lý", "Thao tác sao chép, di chuyển hoặc xóa đang chạy. Hãy hoàn tất trước khi đóng ứng dụng.")
            return
        self.scan_stop.set()
        self.save_settings()
        self.destroy()


def main() -> None:
    app = FileHub()
    app.mainloop()


if __name__ == "__main__":
    main()
