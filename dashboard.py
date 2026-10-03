import tkinter as tk
from tkinter import ttk
import pandas as pd
from datetime import datetime
import time
import csv
import os
import threading
import queue
import sys

from scanner import KaizenScanner
from market import market_is_open

def resource_path(relative_path):
    """Return resource path for development and PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)

    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        relative_path
    )

class ORBDashboard:

    # =========================
    # AUTO REFRESH
    # =========================
    def toggle_auto_refresh(self):

        self.auto_refresh = not self.auto_refresh

        if self.auto_refresh:

            self.auto_button.config(
                text="Auto Refresh ON"
            )

            self.schedule_refresh()

        else:

            self.auto_button.config(
                text="Auto Refresh OFF"
            )

            if self.refresh_job is not None:
                self.root.after_cancel(self.refresh_job)
                self.refresh_job = None

    def schedule_refresh(self):

        if not self.auto_refresh:
            return

        # This callback represents the scheduled refresh itself. Clear the ID
        # before starting so completion can schedule the next cycle.
        self.refresh_job = None

        print("Auto Refresh Running")
        self.run_scan()

    def _schedule_next_auto_refresh(self):
        """Schedule the next cycle after the current scan has completed."""
        if not self.auto_refresh:
            return

        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)

        self.refresh_job = self.root.after(
            45000,
            self.schedule_refresh
        )

    # =========================
    # ALERTS
    # =========================
    def trigger_alert(self, symbol, old_state, new_state, row):

        timestamp = datetime.now().strftime("%H:%M:%S")

        current_time = time.time()

        # Cooldown is tracked by BOTH symbol and new state.
        # This allows an Ignition alert to be followed by an
        # Entry Alert / ORB / HOD alert without being blocked.
        alert_key = (symbol, new_state)

        last_time = self.last_alert_time.get(alert_key, 0)

        if current_time - last_time < self.alert_cooldown:
            return

        self.last_alert_time[alert_key] = current_time

        print(
            f"\n[{timestamp}] ALERT 🚨\n"
            f"{symbol}\n"
            f"{old_state}\n"
            f"↓\n"
            f"{new_state}\n"
            f"Price: {row.get('Price', '')}\n"
            f"RVOL: {row.get('RVOL', '')}\n"
            f"Continuation: {row.get('Continuation', '')}\n"
            f"Ignition Reason: {row.get('IgnitionReason', '')}\n"
        )

        self.log_alert(
            symbol,
            old_state,
            new_state,
            row
        )

        self._add_event(
            f"{symbol}  {new_state}  •  Price {row.get('Price', '')}  •  {row.get('IgnitionReason', '')}"
        )

    def log_alert(
            self,
            symbol,
            old_state,
            new_state,
            row
    ):

        filename = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "alerts.csv"
        )
        print("ALERT FILE PATH:", filename)

        file_exists = os.path.isfile(filename)

        with open(
                filename,
                "a",
                newline="",
                encoding="utf-8"
        ) as f:

            writer = csv.writer(f)

            if not file_exists:
                writer.writerow([
                    "Timestamp",
                    "Symbol",
                    "OldState",
                    "NewState",
                    "Price",
                    "RVOL",
                    "Continuation",
                    "RadarScore",
                    "GainPercent",
                    "IgnitionReason"
                ])

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                old_state,
                new_state,
                row.get("Price", ""),
                row.get("RVOL", ""),
                row.get("Continuation", ""),
                row.get("RadarScore", ""),
                row.get("Gain%", ""),
                row.get("IgnitionReason", "")
            ])

    def update_alert_stats(self):

        filename = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "alerts.csv"
        )
        print("ALERT FILE PATH:", filename)

        if not os.path.exists(filename):

            self.stats_label.config(
                text="No Alert History"
            )

            return

        try:

            alert_columns = [
                "Timestamp",
                "Symbol",
                "OldState",
                "NewState",
                "Price",
                "RVOL",
                "Continuation",
                "RadarScore",
                "GainPercent",
                "IgnitionReason"
            ]

            rows = []

            with open(
                    filename,
                    "r",
                    newline="",
                    encoding="utf-8-sig"
            ) as f:

                reader = csv.reader(f)

                # Skip the historical header.
                next(reader, None)

                for line_number, row in enumerate(
                        reader,
                        start=2
                ):

                    if not row:
                        continue

                    # Legacy Kaizen alert format:
                    # 9 columns, before IgnitionReason was added.
                    if len(row) == 9:
                        row.append("")

                    # Current Kaizen alert format:
                    # 10 columns.
                    elif len(row) == 10:
                        pass

                    else:
                        print(
                            f"ALERT LOAD WARNING: "
                            f"line {line_number} has "
                            f"{len(row)} fields"
                        )
                        continue

                    rows.append(row)

            df = pd.DataFrame(
                rows,
                columns=alert_columns
            )

        except Exception as e:

            print(
                f"ALERT LOAD ERROR: "
                f"{type(e).__name__}: {e}"
            )

            self.stats_label.config(
                text="Error Loading Alerts"
            )

            return

        if df.empty:

            self.stats_label.config(
                text="No Alerts Recorded"
            )

            return

        # Today's alerts only
        try:

            df["Timestamp"] = pd.to_datetime(df["Timestamp"])

            today = pd.Timestamp.now().date()

            df = df[
                df["Timestamp"].dt.date == today
            ]

        except Exception:
            pass

        if df.empty:

            self.stats_label.config(
                text="No Alerts Today"
            )

            return

        transitions = (
            df["OldState"].astype(str)
            + " → "
            + df["NewState"].astype(str)
        )

        counts = transitions.value_counts()

        stats_text = "Today's Alerts\n\n"

        for transition, count in counts.head(5).items():

            stats_text += (
                f"{transition}: {count}\n"
            )

        stats_text += (
            f"\nTotal Alerts: {len(df)}"
        )

        self.stats_label.config(
            text=stats_text
        )

    # =========================
    # INIT
    # =========================
    def __init__(self, root):
        self.root = root
        self.root.iconbitmap(resource_path("Kaizen_V3_Red_Kanji.ico"))
        self.root.title("Kaizen Trading Desk")
        self.root.geometry("1500x900")
        self.root.minsize(1180, 720)

        # ---------- Theme ----------
        self.colors = {
            "bg": "#11151b", "panel": "#171d25", "panel2": "#1d2530",
            "border": "#2b3542", "text": "#e7edf5", "muted": "#8f9baa",
            "accent": "#5aa9ff", "good": "#63d38a", "warn": "#f3c969",
            "bad": "#ef7777", "purple": "#b997ff"
        }
        self.root.configure(bg=self.colors["bg"])
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=self.colors["panel"], foreground=self.colors["text"],
                        fieldbackground=self.colors["panel"], rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background=self.colors["panel2"], foreground=self.colors["text"],
                        relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#294663")], foreground=[("selected", "white")])
        style.configure("TCombobox", fieldbackground=self.colors["panel2"], background=self.colors["panel2"])

        self.scanner = KaizenScanner()
        self.previous_states = {}
        self.auto_refresh = True
        self.refresh_job = None
        self.scan_in_progress = False
        self.scan_results = queue.Queue()
        self.scan_started_at = None
        self.pending_rescan = False
        self.last_scan_df = pd.DataFrame()
        self.last_radar_summary = {}
        self.display_df = pd.DataFrame()
        self.root.after(100, self._poll_scan_results)

        self.hide_wash_var = tk.BooleanVar(value=False)
        self.hod_var = tk.BooleanVar(value=True)
        self.orb_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)
        self.radar_var = tk.BooleanVar(value=True)
        self.ignition_var = tk.BooleanVar(value=True)
        self.reclaim_var = tk.BooleanVar(value=True)
        self.entry_var = tk.BooleanVar(value=True)
        self.mode_var = tk.StringVar(value="combined")
        self.manual_symbol_var = tk.StringVar()
        self.last_alert_time = {}
        self.alert_cooldown = 300

        # ---------- Header ----------
        header = tk.Frame(root, bg=self.colors["bg"], padx=16, pady=12)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=self.colors["bg"])
        title_box.pack(side="left")
        tk.Label(title_box, text="KAIZEN", bg=self.colors["bg"], fg=self.colors["accent"],
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(title_box, text="  TRADING DESK", bg=self.colors["bg"], fg=self.colors["text"],
                 font=("Segoe UI", 18)).pack(side="left")
        self.scan_status_label = tk.Label(header, text="Ready", bg=self.colors["bg"], fg=self.colors["muted"],
                                          font=("Segoe UI", 10, "bold"))
        self.scan_status_label.pack(side="right", padx=(18, 0))
        self.last_scan_label = tk.Label(header, text="Last Scan: Never", bg=self.colors["bg"], fg=self.colors["muted"])
        self.last_scan_label.pack(side="right", padx=18)
        self.status_label = tk.Label(header, text=self.get_status_text(), bg=self.colors["bg"], fg=self.colors["good"],
                                     font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side="right")

        # ---------- Scanner toolbar ----------
        toolbar = tk.Frame(root, bg=self.colors["panel"], padx=12, pady=10,
                           highlightthickness=1, highlightbackground=self.colors["border"])
        toolbar.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(toolbar, text="SCAN MODE", bg=self.colors["panel"], fg=self.colors["muted"],
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))
        ttk.Combobox(toolbar, textvariable=self.mode_var, values=["combined", "movers", "watchlist"],
                     state="readonly", width=12).pack(side="left", padx=(0, 8))
        self.run_button = tk.Button(toolbar, text="▶  Run Scan", command=self.run_scan,
                                    bg="#2367a3", fg="white", activebackground="#2d7abd",
                                    activeforeground="white", relief="flat", padx=12, pady=4)
        self.run_button.pack(side="left", padx=4)
        self.auto_button = tk.Button(toolbar, text="Auto Refresh ON", command=self.toggle_auto_refresh,
                                     bg=self.colors["panel2"], fg=self.colors["text"], relief="flat", padx=10, pady=4)
        self.auto_button.pack(side="left", padx=4)

        for text, var in [("HOD", self.hod_var), ("ORB", self.orb_var), ("Launch", self.launch_var),
                          ("Radar", self.radar_var), ("Ignition", self.ignition_var),
                          ("VWAP", self.reclaim_var), ("Entry", self.entry_var)]:
            tk.Checkbutton(toolbar, text=text, variable=var, command=self.refresh_display_filters,
                           bg=self.colors["panel"], fg=self.colors["text"], selectcolor=self.colors["panel2"],
                           activebackground=self.colors["panel"], activeforeground=self.colors["text"]).pack(side="left", padx=3)
        tk.Checkbutton(toolbar, text="Hide Wash", variable=self.hide_wash_var, command=self.refresh_display_filters,
                       bg=self.colors["panel"], fg=self.colors["muted"], selectcolor=self.colors["panel2"],
                       activebackground=self.colors["panel"], activeforeground=self.colors["text"]).pack(side="right", padx=4)

        # ---------- Main split ----------
        main = tk.PanedWindow(root, orient="horizontal", bg=self.colors["bg"], sashwidth=5, bd=0)
        main.pack(fill="both", expand=True, padx=12)
        left = tk.Frame(main, bg=self.colors["panel"], width=270,
                        highlightthickness=1, highlightbackground=self.colors["border"])
        right = tk.Frame(main, bg=self.colors["bg"])
        main.add(left, minsize=230)
        main.add(right, minsize=780)

        # Left: manual radar/watchlist controls
        tk.Label(left, text="MANUAL RADAR", bg=self.colors["panel"], fg=self.colors["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 8))
        addrow = tk.Frame(left, bg=self.colors["panel"]); addrow.pack(fill="x", padx=10)
        self.manual_symbol_entry = tk.Entry(addrow, textvariable=self.manual_symbol_var, width=10,
                                            bg=self.colors["panel2"], fg=self.colors["text"], insertbackground="white",
                                            relief="flat", font=("Consolas", 11))
        self.manual_symbol_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.manual_symbol_entry.bind("<Return>", lambda event: self.add_manual_symbol())
        tk.Button(addrow, text="+", command=self.add_manual_symbol, bg="#2367a3", fg="white",
                  relief="flat", width=3).pack(side="left", padx=(6, 2), ipady=3)
        tk.Button(addrow, text="−", command=self.remove_manual_symbol, bg=self.colors["panel2"], fg=self.colors["text"],
                  relief="flat", width=3).pack(side="left", padx=2, ipady=3)
        self.manual_radar_label = tk.Label(left, text="None", bg=self.colors["panel"], fg=self.colors["muted"],
                                           justify="left", wraplength=235, anchor="nw")
        self.manual_radar_label.pack(fill="x", padx=12, pady=(8, 16))

        tk.Frame(left, bg=self.colors["border"], height=1).pack(fill="x", padx=10)
        tk.Label(left, text="MARKET PULSE", bg=self.colors["panel"], fg=self.colors["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(14, 8))
        self.pulse_labels = {}
        for key, label in [("tracking", "Tracking"), ("accelerating", "Accelerating"), ("ignition", "Ignition"), ("active", "Active"), ("extended", "Extended"), ("cooling", "Cooling")]:
            rowf = tk.Frame(left, bg=self.colors["panel"]); rowf.pack(fill="x", padx=12, pady=3)
            tk.Label(rowf, text=label, bg=self.colors["panel"], fg=self.colors["muted"]).pack(side="left")
            val = tk.Label(rowf, text="0", bg=self.colors["panel"], fg=self.colors["text"], font=("Segoe UI", 11, "bold"))
            val.pack(side="right"); self.pulse_labels[key] = val
        self.stats_label = tk.Label(left, text="No Alert History", bg=self.colors["panel"], fg=self.colors["muted"],
                                    justify="left", anchor="nw", wraplength=235)
        self.stats_label.pack(fill="both", expand=True, padx=12, pady=(18, 10))

        # Right top: opportunities
        opp = tk.Frame(right, bg=self.colors["panel"], highlightthickness=1, highlightbackground=self.colors["border"])
        opp.pack(fill="both", expand=True)
        tk.Label(opp, text="OPPORTUNITIES", bg=self.colors["panel"], fg=self.colors["text"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
        columns = ["Symbol", "Signal", "Radar", "Lifecycle", "Price", "Gain%", "RVOL", "VolAccel", "RadarScore", "Action"]
        table_frame = tk.Frame(opp, bg=self.colors["panel"]); table_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        widths = {"Symbol":72, "Signal":155, "Radar":105, "Lifecycle":135, "Price":70, "Gain%":68, "RVOL":62,
                  "VolAccel":75, "RadarScore":82, "Action":110}
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths[col], minwidth=55, anchor="center" if col not in ("Signal","Lifecycle","Action") else "w")
        sy = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        sx = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y"); sx.pack(side="bottom", fill="x"); self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        for tag, bg in [("hod","#1d3b2a"),("orb","#18354a"),("launch","#202f4a"),("radar","#18383b"),
                        ("ignition","#4a3c16"),("reclaim","#24314a"),("pullback","#413a1d"),
                        ("extended","#4a2f1f"),("dead","#452626"),("entry","#35264d"),("leader","#1e472c")]:
            self.tree.tag_configure(tag, background=bg, foreground=self.colors["text"])

        # Detail panel
        detail = tk.Frame(right, bg=self.colors["panel"], highlightthickness=1, highlightbackground=self.colors["border"])
        detail.pack(fill="x", pady=(8, 0))
        self.detail_title = tk.Label(detail, text="SELECT A SYMBOL", bg=self.colors["panel"], fg=self.colors["accent"],
                                     font=("Segoe UI", 11, "bold"))
        self.detail_title.pack(anchor="w", padx=12, pady=(10, 4))
        detail_grid = tk.Frame(detail, bg=self.colors["panel"]); detail_grid.pack(fill="x", padx=12, pady=(0, 10))
        self.detail_labels = {}
        fields = [("Price","Price"),("VWAP","VWAP"),("Gain%","Gain"),("VWAP_Ext%","VWAP Ext"),
                  ("RVOL","RVOL"),("RadarScore","Radar Score"),("RadarLifecycle","Radar State"),("RadarVolumeAccel","Vol Accel"),
                  ("RadarPriceAccel%","Price Accel"),("RadarRankAccel","Rank Accel"),("RadarGainAccel","Gain Accel"),("RadarPersistence","Persistence"),
                  ("ORB_High","ORB High"),("ORB_Low","ORB Low"),("Entry","Entry"),("Stop","Stop"),
                  ("T1","T1"),("T2","T2"),("ATR","ATR"),("HOD_Dist%","HOD Dist")]
        for i, (key, label) in enumerate(fields):
            r, c = divmod(i, 4)
            box = tk.Frame(detail_grid, bg=self.colors["panel2"], padx=8, pady=5)
            box.grid(row=r, column=c, sticky="ew", padx=3, pady=3)
            detail_grid.grid_columnconfigure(c, weight=1)
            tk.Label(box, text=label.upper(), bg=self.colors["panel2"], fg=self.colors["muted"], font=("Segoe UI", 7, "bold")).pack(anchor="w")
            value = tk.Label(box, text="—", bg=self.colors["panel2"], fg=self.colors["text"], font=("Segoe UI", 10, "bold"))
            value.pack(anchor="w"); self.detail_labels[key] = value

        # Event feed
        feed = tk.Frame(root, bg=self.colors["panel"], highlightthickness=1, highlightbackground=self.colors["border"])
        feed.pack(fill="x", padx=12, pady=8)
        tk.Label(feed, text="LIVE EVENT FEED", bg=self.colors["panel"], fg=self.colors["text"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(7, 3))
        self.event_feed = tk.Listbox(feed, height=4, bg=self.colors["panel"], fg=self.colors["muted"],
                                     selectbackground="#294663", relief="flat", borderwidth=0,
                                     font=("Consolas", 9))
        self.event_feed.pack(fill="x", padx=8, pady=(0, 8))
        self._add_event("Kaizen Trading Desk ready")
        self.update_manual_radar_label()
        self.schedule_refresh()

    def _add_event(self, message):
        if not hasattr(self, "event_feed"):
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self.event_feed.insert(0, f"{stamp}  {message}")
        while self.event_feed.size() > 50:
            self.event_feed.delete("end")

    def _format_compact_number(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return value if value not in (None, "") else "—"
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        if value >= 1_000:
            return f"{value / 1_000:.1f}K"
        return f"{value:g}"

    def _on_tree_select(self, event=None):
        selection = self.tree.selection()
        if not selection or self.display_df is None or self.display_df.empty:
            return
        symbol = self.tree.item(selection[0], "values")[0]
        matches = self.display_df[self.display_df["Symbol"].astype(str) == str(symbol)]
        if matches.empty:
            return
        row = matches.iloc[0]
        self.detail_title.config(text=f"{symbol}  •  {row.get('State', '')}")
        for key, label in self.detail_labels.items():
            value = row.get(key, "")
            if key in ("Float", "MarketCap"):
                value = self._format_compact_number(value)
            elif value in (None, "") or (isinstance(value, float) and pd.isna(value)):
                value = "—"
            label.config(text=str(value))

    def _update_market_pulse(self, df, radar_summary=None):
        if not hasattr(self, "pulse_labels"):
            return
        if radar_summary is None:
            radar_summary = {
                "tracking": 0, "accelerating": 0, "ignition": 0,
                "active": 0, "extended": 0, "cooling": 0,
            }
            if df is not None and not df.empty and "RadarLifecycle" in df.columns:
                radar_states = df["RadarLifecycle"].astype(str).str.upper()
                radar_summary["tracking"] = len(df)
                for key in ("accelerating", "ignition", "active", "extended", "cooling"):
                    radar_summary[key] = int(radar_states.eq(key.upper()).sum())
        for key, label in self.pulse_labels.items():
            label.config(text=str(radar_summary.get(key, 0)))

    # =========================
    # MANUAL / TOS RADAR
    # =========================

    def add_manual_symbol(self):

        symbol = (
            self.manual_symbol_var
            .get()
            .strip()
            .upper()
        )

        if not symbol:
            return

        added = self.scanner.add_manual_symbol(
            symbol,
            source="MANUAL_TOS"
        )

        self.manual_symbol_var.set("")

        self.update_manual_radar_label()

        if added:
            print(
                f"TOS RADAR -> KAIZEN: "
                f"{symbol}"
            )

            # Request a refresh. If a scan is already running, queue one
            # follow-up scan instead of blocking the UI or overlapping workers.
            self.run_scan()

    def remove_manual_symbol(self):

        symbol = (
            self.manual_symbol_var
            .get()
            .strip()
            .upper()
        )

        if not symbol:
            return

        removed = self.scanner.remove_manual_symbol(
            symbol,
            source="MANUAL_TOS"
        )

        self.manual_symbol_var.set("")

        self.update_manual_radar_label()

        if removed:
            print(
                f"REMOVED FROM MANUAL RADAR: "
                f"{symbol}"
            )

            self.run_scan()

    def update_manual_radar_label(self):

        symbols = (
            self.scanner
            .get_manual_symbols()
        )

        if symbols:

            text = (
                    "Manual Radar: "
                    + ", ".join(symbols)
            )

        else:

            text = "Manual Radar: None"

        self.manual_radar_label.config(
            text=text
        )

    # =========================
    # STATUS
    # =========================
    def get_status_text(self):

        status = (
            "OPEN"
            if market_is_open()
            else "CLOSED"
        )

        return f"Market: {status}"

    # =========================
    # RUN SCAN
    # =========================
    def _capture_filter_state(self):
        """Capture Tkinter variable values on the UI thread."""
        return {
            "hide_wash": self.hide_wash_var.get(),
            "hod": self.hod_var.get(),
            "orb": self.orb_var.get(),
            "launch": self.launch_var.get(),
            "radar": self.radar_var.get(),
            "ignition": self.ignition_var.get(),
            "reclaim": self.reclaim_var.get(),
            "entry": self.entry_var.get(),
        }

    def run_scan(self):
        """Start a scan without blocking Tkinter's main event loop."""

        if self.scan_in_progress:
            # Remember one requested refresh. This is useful when a ticker is
            # added/removed or a filter changes during an active scan.
            self.pending_rescan = True
            self.scan_status_label.config(text="Scan running • refresh queued", fg="darkorange")
            return

        mode = self.mode_var.get()
        filters = self._capture_filter_state()

        self.scan_in_progress = True
        self.pending_rescan = False
        self.scan_started_at = time.time()
        self.run_button.config(state="disabled", text="Scanning…")
        self.scan_status_label.config(text="● Scanning", fg="blue")

        worker = threading.Thread(
            target=self._scan_worker,
            args=(mode, filters),
            daemon=True
        )
        worker.start()

    def _scan_worker(self, mode, filters):
        """Background worker: scanner/network calls only; no Tkinter calls."""
        started = time.time()
        try:
            df = self.scanner.run_scan(mode=mode)
            elapsed = round(time.time() - started, 2)
            radar_summary = self.scanner.get_radar_summary()
            radar_events = self.scanner.drain_radar_events()
            self.scan_results.put(("success", df, elapsed, filters, radar_summary, radar_events))
        except Exception as exc:
            elapsed = round(time.time() - started, 2)
            self.scan_results.put(("error", exc, elapsed, filters, {}, []))

    def _poll_scan_results(self):
        """Apply completed worker results safely on Tkinter's UI thread."""
        try:
            while True:
                kind, payload, elapsed, filters, radar_summary, radar_events = self.scan_results.get_nowait()
                self.scan_in_progress = False
                self.run_button.config(state="normal", text="Run Scan")

                if kind == "error":
                    print("SCAN ERROR:", payload)
                    self.scan_status_label.config(text="Scan error", fg="red")
                    self.last_scan_label.config(text=f"Last Scan: Error ({elapsed}s)")
                else:
                    self.last_scan_df = payload.copy() if payload is not None else pd.DataFrame()
                    self.last_radar_summary = dict(radar_summary or {})
                    df = self._apply_dashboard_filters(self.last_scan_df, filters)
                    self.update_table(df, radar_summary=radar_summary)
                    for event in radar_events:
                        self._add_event(
                            f"{event.get('symbol', '')}  RADAR {event.get('old_state', '')} → {event.get('new_state', '')}  "
                            f"• Score {event.get('score', '')}  • {event.get('reason', '')}"
                        )
                    self.update_alert_stats()
                    self.status_label.config(text=self.get_status_text())

                    scan_time = datetime.now().strftime("%H:%M:%S")
                    self.last_scan_label.config(
                        text=f"Last Scan: {scan_time} ({elapsed}s)"
                    )
                    self.scan_status_label.config(
                        text=f"Ready • {len(df)} setups", fg="green"
                    )
                    self.root.title(
                        f"Kaizen ORB Trading Desk ({len(df)} setups)"
                    )

                # If the user changed the watchlist/filters while scanning, run
                # exactly one fresh scan now that the worker has completed.
                if self.pending_rescan:
                    self.pending_rescan = False
                    self.root.after(10, self.run_scan)
                else:
                    self._schedule_next_auto_refresh()

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._poll_scan_results)

    def refresh_display_filters(self):
        """Re-filter the most recent scan instantly without another API scan."""
        if self.last_scan_df is None or self.last_scan_df.empty:
            return
        filters = self._capture_filter_state()
        df = self._apply_dashboard_filters(self.last_scan_df, filters)
        self.update_table(df, radar_summary=self.last_radar_summary)
        self.scan_status_label.config(
            text=f"Ready • {len(df)} setups", fg="green"
        )
        self.root.title(
            f"Kaizen ORB Trading Desk ({len(df)} setups)"
        )

    def _apply_dashboard_filters(self, df, filters):
        """Apply display-only filters after scanner work has completed."""
        if df is None:
            return pd.DataFrame()

        df = df.copy()

        if (
            filters["hide_wash"]
            and not df.empty
            and "WashStatus" in df.columns
        ):
            df = df[df["WashStatus"] == "CLEAR"]

        allowed_states = []
        state_flags = [
            ("hod", "HOD ATTACK"),
            ("orb", "ORB BREAKOUT"),
            ("launch", "LAUNCH PAD"),
            ("radar", "MARKET RADAR"),
            ("ignition", "MOMENTUM IGNITION"),
            ("reclaim", "VWAP RECLAIM"),
            ("entry", "ENTRY ALERT"),
        ]

        for flag, state in state_flags:
            if filters[flag]:
                allowed_states.append(state)

        if allowed_states and not df.empty and "State" in df.columns:
            df = df[
                df["State"].apply(
                    lambda x: any(
                        state in str(x)
                        for state in allowed_states
                    )
                )
            ]

        return df

    # =========================
    # UPDATE TABLE
    # =========================
    def update_table(self, df, radar_summary=None):
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.display_df = df.copy() if df is not None else pd.DataFrame()
        self._update_market_pulse(self.display_df, radar_summary)

        if df is None or df.empty:
            self.detail_title.config(text="SELECT A SYMBOL")
            for label in self.detail_labels.values():
                label.config(text="—")
            return

        for _, row in df.iterrows():
            symbol = row.get("Symbol", "")
            current_state = row.get("State", "")
            previous_state = self.previous_states.get(symbol)

            important_transitions = [
                ("🔵 LAUNCH PAD", "🟢 ORB BREAKOUT"),
                ("🔷 VWAP RECLAIM", "🟢 ORB BREAKOUT"),
                ("🟡 PULLBACK", "🟢 HOD ATTACK"),
                ("🔵 LAUNCH PAD", "🟢 HOD ATTACK"),
                ("🔷 VWAP RECLAIM", "🟣 ENTRY ALERT"),
                ("⚡ MOMENTUM IGNITION", "🔵 LAUNCH PAD"),
                ("⚡ MOMENTUM IGNITION", "🟣 ENTRY ALERT"),
                ("⚡ MOMENTUM IGNITION", "🟢 ORB BREAKOUT"),
                ("⚡ MOMENTUM IGNITION", "🟢 HOD ATTACK"),
            ]

            entered_ignition = (
                "MOMENTUM IGNITION" in str(current_state).upper()
                and previous_state != current_state
            )
            if entered_ignition:
                self.trigger_alert(symbol, previous_state if previous_state is not None else "NEW DISCOVERY", current_state, row)
            elif (previous_state, current_state) in important_transitions:
                self.trigger_alert(symbol, previous_state, current_state, row)
            self.previous_states[symbol] = current_state

            state = str(current_state).upper()
            lifecycle = str(row.get("Lifecycle", "")).upper()
            if "ENTRY ALERT" in lifecycle: tag = "entry"
            elif "ORB CONFIRMED" in lifecycle: tag = "orb"
            elif "HOD ATTACK" in lifecycle: tag = "hod"
            elif "TREND LEADER" in lifecycle: tag = "leader"
            elif "EXTENDED" in lifecycle: tag = "extended"
            elif "EXIT ZONE" in lifecycle: tag = "dead"
            elif "MOMENTUM IGNITION" in lifecycle: tag = "ignition"
            elif "LAUNCH PAD" in lifecycle: tag = "launch"
            elif "MARKET RADAR" in lifecycle: tag = "radar"
            elif "MOMENTUM" in lifecycle or "DISCOVERY" in lifecycle: tag = "reclaim"
            elif "HOD ATTACK" in state: tag = "hod"
            elif "ORB BREAKOUT" in state: tag = "orb"
            elif "MOMENTUM IGNITION" in state: tag = "ignition"
            elif "MARKET RADAR" in state: tag = "radar"
            elif "ENTRY ALERT" in state: tag = "entry"
            elif "LAUNCH PAD" in state: tag = "launch"
            elif "VWAP RECLAIM" in state: tag = "reclaim"
            elif "PULLBACK" in state: tag = "pullback"
            elif "EXTENDED" in state: tag = "extended"
            else: tag = "dead"

            self.tree.insert("", "end", values=(
                symbol,
                row.get("State", ""),
                row.get("RadarLifecycle", ""),
                row.get("Lifecycle", ""),
                row.get("Price", ""),
                row.get("Gain%", ""),
                row.get("RVOL", ""),
                row.get("RadarVolumeAccel", ""),
                row.get("RadarScore", ""),
                row.get("Action", ""),
            ), tags=(tag,))

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self._on_tree_select()


# =========================
# RUN APP
# =========================
if __name__ == "__main__":

    root = tk.Tk()

    app = ORBDashboard(root)

    root.mainloop()