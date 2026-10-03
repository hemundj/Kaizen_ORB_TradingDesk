import tkinter as tk
from tkinter import ttk
import pandas as pd
from datetime import datetime
import time
import csv
import os
import threading
import queue

from scanner import KaizenScanner
from market import market_is_open


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
        self.root.title("Kaizen ORB Trading Desk")
        self.root.geometry("1450x780")
        self.root.minsize(1050, 620)

        self.scanner = KaizenScanner()

        self.previous_states = {}

        self.auto_refresh = True

        self.refresh_job = None

        # Background scan worker state. Tkinter widgets must only be touched
        # from the main UI thread; scanner/network work runs in a worker.
        self.scan_in_progress = False
        self.scan_results = queue.Queue()
        self.scan_started_at = None
        self.pending_rescan = False
        self.last_scan_df = pd.DataFrame()

        # Poll worker results without blocking the Tkinter event loop.
        self.root.after(100, self._poll_scan_results)

        # =========================
        # TOP CONTROL PANEL
        # =========================
        control_frame = tk.Frame(root)
        control_frame.pack(fill="x", pady=5)

        self.hide_wash_var = tk.BooleanVar(value=False)
        self.hod_var = tk.BooleanVar(value=True)
        self.orb_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)
        self.radar_var = tk.BooleanVar(value=True)
        self.ignition_var = tk.BooleanVar(value=True)
        self.reclaim_var = tk.BooleanVar(value=True)
        self.entry_var = tk.BooleanVar(value=True)

        tk.Checkbutton(
            control_frame,
            text="HOD Attack",
            variable=self.hod_var,
            command=self.refresh_display_filters
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="ORB Breakout",
            variable=self.orb_var,
            command=self.refresh_display_filters
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="Launch Pad",
            variable=self.launch_var,
            command=self.refresh_display_filters
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="Market Radar",
            variable=self.radar_var,
            command=self.refresh_display_filters
        ).pack(side="left", padx=5)

        # NEW
        tk.Checkbutton(
            control_frame,
            text="Momentum Ignition",
            variable=self.ignition_var,
            command=self.refresh_display_filters
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="VWAP Reclaim",
            variable=self.reclaim_var,
            command=self.refresh_display_filters
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="Entry Alert",
            variable=self.entry_var,
            command=self.refresh_display_filters
        ).pack(side="left", padx=5)

        tk.Label(
            control_frame,
            text="Scan Mode:"
        ).pack(side="left", padx=5)

        self.mode_var = tk.StringVar(
            value="combined"
        )

        mode_dropdown = ttk.Combobox(
            control_frame,
            textvariable=self.mode_var,
            values=[
                "combined",
                "movers",
                "watchlist"
            ],
            state="readonly",
            width=15
        )

        mode_dropdown.pack(
            side="left",
            padx=5
        )

        self.run_button = tk.Button(
            control_frame,
            text="Run Scan",
            command=self.run_scan
        )

        self.run_button.pack(
            side="left",
            padx=5
        )

        # =========================
        # REFRESH BUTTON
        # =========================
        self.auto_button = tk.Button(
            control_frame,
            text=(
                "Auto Refresh ON"
                if self.auto_refresh
                else "Auto Refresh OFF"
            ),
            command=self.toggle_auto_refresh
        )

        self.auto_button.pack(
            side="left",
            padx=5
        )

        self.status_label = tk.Label(
            control_frame,
            text=self.get_status_text(),
            fg="blue"
        )

        self.status_label.pack(
            side="right",
            padx=10
        )

        self.last_scan_label = tk.Label(
            control_frame,
            text="Last Scan: Never",
            fg="green"
        )

        self.last_scan_label.pack(
            side="right",
            padx=10
        )

        self.scan_status_label = tk.Label(
            control_frame,
            text="Ready",
            fg="gray"
        )
        self.scan_status_label.pack(
            side="right",
            padx=10
        )

        tk.Checkbutton(
            control_frame,
            text="Hide Wash Risk",
            variable=self.hide_wash_var,
            command=self.refresh_display_filters
        ).pack(
            side="left",
            padx=5
        )

        self.stats_label = tk.Label(
            self.root,
            text="No Alert History",
            justify="left",
            anchor="w"
        )

        self.stats_label.pack(
            fill="x",
            padx=5,
            pady=5
        )

        # Cooldown remains 5 minutes,
        # but it now applies to each (symbol, state) pair.
        self.last_alert_time = {}
        self.alert_cooldown = 300

        # =========================
        # MANUAL / TOS RADAR
        # =========================

        manual_frame = tk.Frame(
            self.root
        )

        manual_frame.pack(
            fill="x",
            padx=5,
            pady=(0, 5)
        )

        tk.Label(
            manual_frame,
            text="TOS Radar:"
        ).pack(
            side="left",
            padx=(0, 5)
        )

        self.manual_symbol_var = tk.StringVar()

        self.manual_symbol_entry = tk.Entry(
            manual_frame,
            textvariable=self.manual_symbol_var,
            width=10
        )

        self.manual_symbol_entry.pack(
            side="left",
            padx=5
        )

        self.manual_symbol_entry.bind(
            "<Return>",
            lambda event: self.add_manual_symbol()
        )

        tk.Button(
            manual_frame,
            text="+ Add",
            command=self.add_manual_symbol
        ).pack(
            side="left",
            padx=5
        )

        tk.Button(
            manual_frame,
            text="- Remove",
            command=self.remove_manual_symbol
        ).pack(
            side="left",
            padx=5
        )

        self.manual_radar_label = tk.Label(
            manual_frame,
            text="Manual Radar: None",
            anchor="w"
        )

        self.manual_radar_label.pack(
            side="left",
            padx=15
        )

        # =========================
        # TABLE
        # =========================
        columns = [
            "Symbol",
            "Lifecycle",
            "Action",
            "State",

            #"ORB",
            #"TradeEligible",
            #"Opportunity",
            #"Float",
            #"MarketCap",
            #"Grade",
            #"Upside%",
            #"VWAP_Ext%",
            #"WashStatus",
            #"VWAP",
            #"ORB_High",
            #"ContGrade",

            "FloatTurnover%",
            "RVOL",
            "Continuation",
            "RadarScore",
            "Score",

            #"ATR",
            #"ORB_Low",
            #"ORB_Break",
            #"Premarket",
            #"EarlySignal",

            "Gain%",
            "Setup",
            "Price",
            "Entry",
            "Stop",
            "T1",
            "T2",

            #"T3"
        ]

        self.tree = ttk.Treeview(
            root,
            columns=columns,
            show="headings"
        )

        # =========================
        # ROW COLORS
        # =========================
        self.tree.tag_configure("hod",background="#ccffcc")
        self.tree.tag_configure("orb",background="#d9f2ff")
        self.tree.tag_configure("launch",background="#e6f0ff")
        self.tree.tag_configure("radar",background="#e6ffff")
        # NEW
        self.tree.tag_configure("ignition",background="#fff0b3")
        self.tree.tag_configure("reclaim",background="#f0f5ff")
        self.tree.tag_configure("pullback",background="#fff7cc")
        self.tree.tag_configure("extended",background="#ffe6cc")
        self.tree.tag_configure("dead",background="#ffe6e6")
        self.tree.tag_configure("entry",background="#d6b3ff")
        self.tree.tag_configure("leader",background="#7dff7d")

        for col in columns:

            self.tree.heading(
                col,
                text=col
            )

            self.tree.column(
                col,
                width=90
            )

        # -------------------------
        # Custom column widths
        # -------------------------
        self.tree.column(
            "Symbol",
            width=70
        )

        self.tree.column(
            "Lifecycle",
            width=180
        )

        self.tree.column(
            "Action",
            width=140
        )

        self.tree.column(
            "State",
            width=170
        )

        self.tree.column(
            "Price",
            width=70
        )

        self.tree.column(
            "RVOL",
            width=70
        )

        self.tree.column(
            "Gain%",
            width=75
        )

        self.tree.column(
            "RadarScore",
            width=85
        )

        self.tree.column(
            "Score",
            width=70
        )

        self.tree.column(
            "Setup",
            width=110
        )

        self.tree.column(
            "Entry",
            width=70
        )

        self.tree.column(
            "Stop",
            width=70
        )

        self.tree.column(
            "T1",
            width=70
        )

        self.tree.column(
            "T2",
            width=70
        )

        # Scrollbars keep the opportunity table usable on smaller screens.
        tree_scroll_y = ttk.Scrollbar(
            root, orient="vertical", command=self.tree.yview
        )
        tree_scroll_x = ttk.Scrollbar(
            root, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set
        )

        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x.pack(side="bottom", fill="x")
        self.tree.pack(
            fill="both",
            expand=True
        )

        # Start auto-refresh on launch. The scan itself runs in a worker, so
        # startup remains responsive even when fundamentals must be fetched.
        self.schedule_refresh()

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
            self.scan_results.put(("success", df, elapsed, filters))
        except Exception as exc:
            elapsed = round(time.time() - started, 2)
            self.scan_results.put(("error", exc, elapsed, filters))

    def _poll_scan_results(self):
        """Apply completed worker results safely on Tkinter's UI thread."""
        try:
            while True:
                kind, payload, elapsed, filters = self.scan_results.get_nowait()
                self.scan_in_progress = False
                self.run_button.config(state="normal", text="Run Scan")

                if kind == "error":
                    print("SCAN ERROR:", payload)
                    self.scan_status_label.config(text="Scan error", fg="red")
                    self.last_scan_label.config(text=f"Last Scan: Error ({elapsed}s)")
                else:
                    self.last_scan_df = payload.copy() if payload is not None else pd.DataFrame()
                    df = self._apply_dashboard_filters(self.last_scan_df, filters)
                    self.update_table(df)
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
        self.update_table(df)
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
    def update_table(self, df):

        # Clear old rows
        for row in self.tree.get_children():
            self.tree.delete(row)

        if df is None or df.empty:
            return

        for _, row in df.iterrows():

            symbol = row["Symbol"]

            current_state = row["State"]

            previous_state = (
                self.previous_states.get(symbol)
            )

            # ==========================================
            # IMPORTANT STATE TRANSITIONS
            # ==========================================
            important_transitions = [

                (
                    "🔵 LAUNCH PAD",
                    "🟢 ORB BREAKOUT"
                ),

                (
                    "🔷 VWAP RECLAIM",
                    "🟢 ORB BREAKOUT"
                ),

                (
                    "🟡 PULLBACK",
                    "🟢 HOD ATTACK"
                ),

                (
                    "🔵 LAUNCH PAD",
                    "🟢 HOD ATTACK"
                ),

                (
                    "🔷 VWAP RECLAIM",
                    "🟣 ENTRY ALERT"
                ),

                # NEW
                (
                    "⚡ MOMENTUM IGNITION",
                    "🔵 LAUNCH PAD"
                ),

                (
                    "⚡ MOMENTUM IGNITION",
                    "🟣 ENTRY ALERT"
                ),

                (
                    "⚡ MOMENTUM IGNITION",
                    "🟢 ORB BREAKOUT"
                ),

                (
                    "⚡ MOMENTUM IGNITION",
                    "🟢 HOD ATTACK"
                ),
            ]

            # ==========================================
            # MOMENTUM IGNITION ALERT
            # ==========================================
            entered_ignition = (
                "MOMENTUM IGNITION"
                in str(current_state).upper()
                and previous_state != current_state
            )

            if entered_ignition:

                ignition_old_state = (
                    previous_state
                    if previous_state is not None
                    else "NEW DISCOVERY"
                )

                self.trigger_alert(
                    symbol,
                    ignition_old_state,
                    current_state,
                    row
                )

            # ==========================================
            # CONFIRMED ALERT TRANSITIONS
            # ==========================================
            elif (
                    previous_state,
                    current_state
            ) in important_transitions:

                self.trigger_alert(
                    symbol,
                    previous_state,
                    current_state,
                    row
                )

            self.previous_states[symbol] = current_state

            state = str(row.get("State","")).upper()

            lifecycle = str(row.get("Lifecycle","")).upper()

            tag = ""

            # ==========================================
            # LIFECYCLE COLORS
            # ==========================================
            if "ENTRY ALERT" in lifecycle:
                tag = "entry"

            elif "ORB CONFIRMED" in lifecycle:
                tag = "orb"

            elif "HOD ATTACK" in lifecycle:
                tag = "hod"

            elif "TREND LEADER" in lifecycle:
                tag = "leader"

            elif "EXTENDED" in lifecycle:
                tag = "extended"

            elif "EXIT ZONE" in lifecycle:
                tag = "dead"

            elif "MOMENTUM IGNITION" in lifecycle:
                tag = "ignition"

            elif "LAUNCH PAD" in lifecycle:
                tag = "launch"

            elif "MARKET RADAR" in lifecycle:
                tag = "radar"

            elif "MOMENTUM" in lifecycle:
                tag = "reclaim"

            elif "DISCOVERY" in lifecycle:
                tag = "reclaim"

            # ==========================================
            # FALLBACK TO STATE
            # ==========================================
            elif "HOD ATTACK" in state:
                tag = "hod"

            elif "ORB BREAKOUT" in state:
                tag = "orb"

            elif "MOMENTUM IGNITION" in state:
                tag = "ignition"

            elif "MARKET RADAR" in state:
                tag = "radar"

            elif "ENTRY ALERT" in state:
                tag = "entry"

            elif "LAUNCH PAD" in state:
                tag = "launch"

            elif "VWAP RECLAIM" in state:
                tag = "reclaim"

            elif "PULLBACK" in state:
                tag = "pullback"

            elif "EXTENDED" in state:
                tag = "extended"

            else:
                tag = "dead"

            print(
                symbol,
                tag,
                state
            )

            self.tree.insert(
                "",
                "end",
                values=(
                    row.get("Symbol", ""),
                    row.get("Lifecycle", ""),
                    row.get("Action", ""),
                    row.get("State", ""),
                    row.get("FloatTurnover%",""),
                    row.get("RVOL",""),
                    row.get("Continuation",""),
                    row.get("RadarScore", ""),
                    row.get("Score",""),
                    row.get("Gain%",""),
                    row.get("Setup",""),
                    row.get("Price",""),
                    row.get("Entry",""),
                    row.get("Stop",""),
                    row.get("T1",""),
                    row.get("T2",""),
                ),
                tags=(tag,)
            )


# =========================
# RUN APP
# =========================
if __name__ == "__main__":

    root = tk.Tk()

    app = ORBDashboard(root)

    root.mainloop()