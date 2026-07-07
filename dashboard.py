import tkinter as tk
from tkinter import ttk
import pandas as pd
from datetime import datetime
import time

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

    def __init__(self, root):
        self.root = root
        self.root.title("Kaizen ORB Trading Desk")
        self.root.geometry("1100x600")

        self.scanner = KaizenScanner()

        self.auto_refresh = False

        # =========================
        # TOP CONTROL PANEL
        # =========================
        control_frame = tk.Frame(root)
        control_frame.pack(fill="x", pady=5)

        tk.Label(control_frame, text="Scan Mode:").pack(side="left", padx=5)

        self.mode_var = tk.StringVar(value="watchlist")

        mode_dropdown = ttk.Combobox(
            control_frame,
            textvariable=self.mode_var,
            values=["watchlist", "movers", "combined"],
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



        # =========================
        # TABLE (RESULTS)
        # =========================
        columns = [
            "Symbol",
            "Opportunity",
            #"Grade",
            "VWAP",
            "ORB_High",
            "Price",
            #"ContGrade",
            #"Continuation",
            "RVOL",
            "ATR",
            #"ORB_Low",
            #"ORB_Break",
            "Premarket",
            "EarlySignal",
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

        elapsed = round(time.time() - start, 2)

        self.update_table(df)

        self.status_label.config(
            text=self.get_status_text()
        )

        scan_time = datetime.now().strftime("%H:%M:%S")

        self.last_scan_label.config(
            text=f"Last Scan: {scan_time} ({elapsed}s)"
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

            self.tree.insert("", "end", values=(
                row.get("Symbol", ""),
                row.get("Opportunity", ""),
                #row.get("Grade", ""),
                row.get("VWAP", ""),
                row.get("ORB_High", ""),
                row.get("Price", ""),
                #row.get("ContGrade",""),
                #row.get("Continuation", ""),
                row.get("RVOL",""),
                row.get("ATR",""),
                #row.get("ORB_Low",""),
                #row.get("ORB_Break",""),
                row.get("Premarket",""),
                row.get("EarlySignal",""),
                row.get("Gain%", ""),
                row.get("Score", ""),
                row.get("Setup", ""),
                row.get("Entry", ""),
                row.get("Stop", ""),
                row.get("T1", ""),
                row.get("T2", ""),
                #row.get("T3", "")
            ))


# =========================
# RUN APP
# =========================
if __name__ == "__main__":

    root = tk.Tk()
    app = ORBDashboard(root)

    root.mainloop()