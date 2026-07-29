import tkinter as tk
from tkinter import ttk
import pandas as pd
from datetime import datetime
import time
import csv
import os



from scanner import KaizenScanner
from market import market_is_open




class ORBDashboard:
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

    def schedule_refresh(self):

        if self.auto_refresh:
            print("Auto Refresh Running")

            self.run_scan()

            self.root.after(
                45000,
                self.schedule_refresh
            )

    def trigger_alert(self, symbol, old_state, new_state, row):

        timestamp = datetime.now().strftime("%H:%M:%S")

        current_time = time.time()

        last_time = self.last_alert_time.get(symbol,0)

        if (current_time - last_time < self.alert_cooldown):
            return

        self.last_alert_time[symbol] = current_time

        print(
            f"\n[{timestamp}] ALERT 🚨\n"
            f"{symbol}\n"
            f"{old_state}\n"
            f"↓\n"
            f"{new_state}\n"
            f"Price: {row['Price']}\n"
            f"RVOL: {row['RVOL']}\n"
            f"Continuation: {row['Continuation']}\n"
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

        filename = "alerts.csv"

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
                    "GainPercent"
                ])

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                old_state,
                new_state,
                row.get("Price", ""),
                row.get("RVOL", ""),
                row.get("Continuation", ""),
                row.get("Gain%", "")
            ])

    def update_alert_stats(self):

        filename = "alerts.csv"

        if not os.path.exists(filename):
            self.stats_label.config(
                text="No Alert History"
            )

            return

        try:

            df = pd.read_csv(filename)


        except Exception:

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
                df["OldState"]
                + " → "
                + df["NewState"]
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



    def __init__(self, root):
        self.root = root
        self.root.title("Kaizen ORB Trading Desk")
        self.root.geometry("1100x600")

        self.scanner = KaizenScanner()

        self.previous_states = {}

        self.auto_refresh = False

        # =========================
        # TOP CONTROL PANEL
        # =========================
        control_frame = tk.Frame(root)
        control_frame.pack(fill="x", pady=5)

        self.hide_wash_var = tk.BooleanVar(value=False)
        self.hod_var = tk.BooleanVar(value=True)
        self.orb_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)
        self.reclaim_var = tk.BooleanVar(value=True)
        self.entry_var = tk.BooleanVar(value=True)

        tk.Checkbutton(
            control_frame,
            text="HOD Attack",
            variable=self.hod_var,
            command = self.run_scan
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="ORB Breakout",
            variable=self.orb_var,
            command=self.run_scan
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="Launch Pad",
            variable=self.launch_var,
            command=self.run_scan
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="VWAP Reclaim",
            variable=self.reclaim_var,
            command=self.run_scan
        ).pack(side="left", padx=5)

        tk.Checkbutton(
            control_frame,
            text="Entry Alert",
            variable=self.entry_var,
            command=self.run_scan
        ).pack(side="left", padx=5)

        tk.Label(control_frame, text="Scan Mode:").pack(side="left", padx=5)

        self.mode_var = tk.StringVar(value="combined")

        mode_dropdown = ttk.Combobox(
            control_frame,
            textvariable=self.mode_var,
            values=["combined", "movers", "watchlist"],
            state="readonly",
            width=15
        )
        mode_dropdown.pack(side="left", padx=5)

        self.run_button = tk.Button(
            control_frame,
            text="Run Scan",
            command=self.run_scan
        )
        self.run_button.pack(side="left", padx=5)

        #==========================
        # Refresh Button
        #==========================

        self.auto_button = tk.Button(
            control_frame,
            text="Auto Refresh OFF",
            command=self.toggle_auto_refresh
        )
        self.auto_button.pack(side="left", padx=5)

        self.status_label = tk.Label(
            control_frame,
            text=self.get_status_text(),
            fg="blue"
        )
        self.status_label.pack(side="right", padx=10)

        self.last_scan_label = tk.Label(
            control_frame,
            text="Last Scan: Never",
            fg="green"
        )

        self.last_scan_label.pack(side="right", padx=10)

        tk.Checkbutton(
            control_frame,
            text="Hide Wash Risk",
            variable=self.hide_wash_var
        ).pack(side="left", padx=5)

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

        self.last_alert_time = {}
        self.alert_cooldown = 300

        # =========================
        # TABLE (RESULTS)
        # =========================
        columns = [
            "Symbol",
            "State",
            "ORB",
            "TradeEligible",
            "Opportunity",
            #"Grade",
            "Upside%",
            #"WashStatus",
            "VWAP",

            #"ORB_High",
            "Price",
            #"ContGrade",
            #"Continuation",
            "RVOL",
            "ATR",
            #"ORB_Low",
            #"ORB_Break",
            #"Premarket",
            #"EarlySignal",
            "Gain%",
            "Score",
            "Setup",
            "Entry",
            "Stop",
            "T1",
            "T2",
            #"T3"
        ]

        self.tree = ttk.Treeview(root, columns=columns, show="headings")



        # ==================================
        # ROW COLORS
        # ==================================

        self.tree.tag_configure(
            "hod",
            background="#ccffcc"
        )

        self.tree.tag_configure(
            "orb",
            background="#d9f2ff"
        )

        self.tree.tag_configure(
            "launch",
            background="#e6f0ff"
        )

        self.tree.tag_configure(
            "reclaim",
            background="#f0f5ff"
        )

        self.tree.tag_configure(
            "pullback",
            background="#fff7cc"
        )

        self.tree.tag_configure(
            "extended",
            background="#ffe6cc"
        )

        self.tree.tag_configure(
            "dead",
            background="#ffe6e6"
        )

        self.tree.tag_configure(
            "entry",
            background="#d6b3ff"
        )

        self.tree.tag_configure(
            "leader",
            background="#7dff7d"
        )

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=90)

        self.tree.pack(fill="both", expand=True)

    # =========================
    # STATUS
    # =========================
    def get_status_text(self):

        status = "OPEN" if market_is_open() else "CLOSED"
        return f"Market: {status}"

    # =========================
    # RUN SCAN
    # =========================
    def run_scan(self):

        start = time.time()

        mode = self.mode_var.get()

        df = self.scanner.run_scan(mode=mode)

        if (
                self.hide_wash_var.get()
                and not df.empty
                and "WashStatus" in df.columns
        ):
            df = df[
                df["WashStatus"] == "CLEAR"
                ]

        allowed_states = []

        if self.hod_var.get():
            allowed_states.append("HOD ATTACK")

        if self.orb_var.get():
            allowed_states.append("ORB BREAKOUT")

        if self.launch_var.get():
            allowed_states.append("LAUNCH PAD")

        if self.reclaim_var.get():
            allowed_states.append("VWAP RECLAIM")

        if self.entry_var.get():
            allowed_states.append("ENTRY ALERT")

        if allowed_states and not df.empty:
            df = df[
                df["State"].apply(
                    lambda x: any(
                        state in str(x)
                        for state in allowed_states
                    )
                )
            ]

        elapsed = round(time.time() - start, 2)

        self.update_table(df)

        self.update_alert_stats()

        self.status_label.config(
            text=self.get_status_text()
        )

        scan_time = datetime.now().strftime("%H:%M:%S")

        self.last_scan_label.config(
            text=f"Last Scan: {scan_time} ({elapsed}s)"
        )

        self.root.title(
            f"Kaizen ORB Dashboard ({len(df)} setups)"

    )



    # =========================
    # UPDATE TABLE
    # =========================
    def update_table(self, df):

        # clear old rows
        for row in self.tree.get_children():
            self.tree.delete(row)

        if df is None or df.empty:
            return

        for _, row in df.iterrows():

            symbol = row["Symbol"]
            current_state = row["State"]

            previous_state = self.previous_states.get(symbol)

            important_transitions = [

                ("🔵 LAUNCH PAD", "🟢 ORB BREAKOUT"),

                ("🔷 VWAP RECLAIM", "🟢 ORB BREAKOUT"),

                ("🟡 PULLBACK", "🟢 HOD ATTACK"),

                ("🔵 LAUNCH PAD", "🟢 HOD ATTACK"),

                ("🔷 VWAP RECLAIM", "🟣 ENTRY ALERT"),
            ]

            if (
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

            state = row.get("State", "")

            tag = ""

            if "HOD ATTACK" in state:
                tag = "hod"

            elif "TREND LEADER" in state:
                tag = "leader"

            elif "ORB BREAKOUT" in state:
                tag = "orb"

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

            print(symbol, tag, state)
            self.tree.insert(
                "",
                "end",
                values=(
                    row.get("Symbol", ""),
                    row.get("State", ""),
                    row.get("ORB", ""),
                    row.get("TradeEligible", ""),
                    row.get("Opportunity", ""),
                    # row.get("Grade", ""),
                    row.get("Upside%",""),
                    #row.get("WashStatus", ""),
                    row.get("VWAP", ""),

                    # row.get("ORB_High", ""),
                    row.get("Price", ""),
                    # row.get("ContGrade", ""),
                    # row.get("Continuation", ""),
                    row.get("RVOL", ""),
                    row.get("ATR", ""),
                    # row.get("ORB_Low", ""),
                    # row.get("ORB_Break", ""),
                    # row.get("Premarket", ""),
                    # row.get("EarlySignal", ""),
                    row.get("Gain%", ""),
                    row.get("Score", ""),
                    row.get("Setup", ""),
                    row.get("Entry", ""),
                    row.get("Stop", ""),
                    row.get("T1", ""),
                    row.get("T2", ""),
                    # row.get("T3", "")
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