import requests
import pandas as pd
import csv
import os

from datetime import datetime

from config import (
    API_KEY,
    SECRET_KEY,
    DISCOVERY_MIN_PRICE,
    MIN_PRICE,
    MAX_PRICE,
    MIN_GAIN,
    MIN_SCORE,
    DEBUG_MODE
)

from watchlist import WATCHLIST
from grading import grade_score
from indicators import (
    calc_atr,
    calc_vwap,
    orb_levels,
    volume_spike,
    calculate_rvol,
    rvol_score,
    near_hod
    )

from trade_journal import TradeJournal

class KaizenScanner:

    def __init__(self):

        self.headers = {
            "APCA-API-KEY-ID": API_KEY.strip(),
            "APCA-API-SECRET-KEY": SECRET_KEY.strip()
        }

        self.base_url = "https://data.alpaca.markets"
        self.trade_journal = TradeJournal()

        # Track the previous mover list so we can detect entries and exits
        self.previous_movers = set()
        self.discovery_seen_date = datetime.now().date()
        self.movers_initialized = False

    # ==================================================
    # DATA
    # ==================================================

    def get_movers(self):

        url = (
            f"{self.base_url}"
            f"/v1beta1/screener/stocks/movers"
        )

        try:
            r = requests.get(
                url,
                headers=self.headers,
                params={"top": 50},
                timeout=15
            )

            if DEBUG_MODE:
                print("MOVERS STATUS:", r.status_code)

            if r.status_code != 200:

                if DEBUG_MODE:
                    print(
                        "MOVERS API ERROR:",
                        r.text[:500]
                    )

                return []

            data = r.json()

            gainers = data.get("gainers", [])

            if DEBUG_MODE and gainers:
                print(
                    "SAMPLE MOVER DATA:",
                    gainers[0]
                )

            if DEBUG_MODE:
                print(
                    "RAW GAINERS COUNT:",
                    len(gainers)
                )

            clean_symbols = []
            discovery_rows = []

            for rank, g in enumerate(
                    gainers,
                    start=1
            ):

                symbol = g.get("symbol", "")

                if not symbol:
                    continue

                if (
                        "." in symbol
                        or symbol.endswith("W")
                        or symbol.endswith("R")
                        or symbol.endswith("U")
                ):
                    continue

                clean_symbols.append(symbol)

                discovery_rows.append({
                    "symbol": symbol,
                    "rank": rank,
                    "price": g.get("price", ""),
                    "change": g.get("change", ""),
                    "percent_change": g.get(
                        "percent_change",
                        ""
                    )
                })

            if DEBUG_MODE:
                print(
                    "CLEAN MOVERS COUNT:",
                    len(clean_symbols)
                )

                print(
                    "CLEAN MOVERS:",
                    clean_symbols
                )

            print(
                "ABOUT TO LOG DISCOVERY:",
                len(discovery_rows)
            )

            self.log_discovery_timeline(
                discovery_rows
            )

            print("DISCOVERY LOG FINISHED")

            return clean_symbols

        except Exception as e:

            print(

                "MOVERS EXCEPTION:",

                type(e).__name__,

                e

            )

        return []

    def log_discovery_timeline(self, mover_rows):

        project_folder = os.path.dirname(
            os.path.abspath(__file__)
        )

        filename = os.path.join(
            project_folder,
            "discovery_timeline.csv"
        )

        print("CURRENT WORKING DIRECTORY:", os.getcwd())
        print("DISCOVERY FILE PATH:", filename)

        # Reset first-seen memory when the date changes
        current_date = datetime.now().date()

        if current_date != self.discovery_seen_date:
            self.discovery_seen_symbols.clear()
            self.discovery_seen_date = current_date

        file_exists = os.path.isfile(filename)

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        try:
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
                        "Rank",
                        "MoverPrice",
                        "Change",
                        "PercentChange",
                        "FirstSeen",
                        "Source"
                    ])

                for mover in mover_rows:
                    symbol = mover.get("symbol", "")

                    first_seen = (
                            symbol not in self.discovery_seen_symbols
                    )

                    writer.writerow([
                        timestamp,
                        symbol,
                        mover.get("rank", ""),
                        mover.get("price", ""),
                        mover.get("change", ""),
                        mover.get("percent_change", ""),
                        "YES" if first_seen else "",
                        "ALPACA_MOVERS"
                    ])

                    self.discovery_seen_symbols.add(symbol)
            print(
                "DISCOVERY FILE EXISTS:",
                os.path.exists(filename)
            )

            print(
                "DISCOVERY FILE SIZE:",
                os.path.getsize(filename)
                if os.path.exists(filename)
                else "MISSING"
            )
        except Exception as e:
            if DEBUG_MODE:
                print(
                    "DISCOVERY TIMELINE ERROR:",
                    e
                )

    def log_discovery_timeline(self, mover_rows):

        project_folder = os.path.dirname(
            os.path.abspath(__file__)
        )

        filename = os.path.join(
            project_folder,
            "discovery_events.csv"
        )

        current_date = datetime.now().date()

        # Reset tracking at the beginning of a new day
        if current_date != self.discovery_seen_date:
            self.previous_movers = set()
            self.discovery_seen_date = current_date
            self.movers_initialized = False

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Build the current mover symbol set
        current_movers = {
            mover.get("symbol", "")
            for mover in mover_rows
            if mover.get("symbol")
        }

        # Keep lookup data for ranks, prices, and changes
        mover_lookup = {
            mover.get("symbol"): mover
            for mover in mover_rows
            if mover.get("symbol")
        }

        # On the first scan of the session, treat all current movers as entries
        if not self.movers_initialized:
            entered_symbols = current_movers
            exited_symbols = set()
            self.movers_initialized = True

        else:
            entered_symbols = (
                    current_movers - self.previous_movers
            )

            exited_symbols = (
                    self.previous_movers - current_movers
            )

        # Nothing changed, so do not write anything
        if not entered_symbols and not exited_symbols:
            self.previous_movers = current_movers
            return

        file_exists = os.path.isfile(filename)

        try:
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
                        "Event",
                        "Rank",
                        "MoverPrice",
                        "Change",
                        "PercentChange",
                        "Source"
                    ])

                # Log new entries
                for symbol in sorted(entered_symbols):
                    mover = mover_lookup.get(symbol, {})

                    writer.writerow([
                        timestamp,
                        symbol,
                        "ENTRY",
                        mover.get("rank", ""),
                        mover.get("price", ""),
                        mover.get("change", ""),
                        mover.get("percent_change", ""),
                        "ALPACA_MOVERS"
                    ])

                # Log exits
                for symbol in sorted(exited_symbols):
                    writer.writerow([
                        timestamp,
                        symbol,
                        "EXIT",
                        "",
                        "",
                        "",
                        "",
                        "ALPACA_MOVERS"
                    ])

            if DEBUG_MODE:
                print(
                    f"DISCOVERY EVENTS: "
                    f"{len(entered_symbols)} entries, "
                    f"{len(exited_symbols)} exits"
                )

        except Exception as e:
            print(
                "DISCOVERY EVENT ERROR:",
                type(e).__name__,
                e
            )

        # Save current list for comparison with the next scan
        self.previous_movers = current_movers

    def get_snapshot(self, symbols):

        if not symbols:
            return {}

        url = f"{self.base_url}/v2/stocks/snapshots"

        try:
            r = requests.get(
                url,
                headers=self.headers,
                params={"symbols": ",".join(symbols)},
                timeout=15
            )

            if r.status_code != 200:
                return {}

            return r.json()

        except Exception:
            return {}

    def get_bars(self, symbol, timeframe="5Min", limit=200):

        url = f"{self.base_url}/v2/stocks/{symbol}/bars"

        params = {
            "timeframe": timeframe,
            "limit": limit,
            "feed": "iex"
        }

        try:
            import time

            start = time.time()

            r = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=15
            )

            print(symbol, "took", round(time.time() - start, 2), "seconds")

            if r.status_code != 200:
                return []

            data = r.json()

            bars = data.get("bars")

            if not bars:
                return []

            # normalize
            clean = []
            for b in bars:
                if not all(k in b for k in ["o", "h", "l", "c", "v"]):
                    continue

                clean.append({
                    "o": float(b["o"]),
                    "h": float(b["h"]),
                    "l": float(b["l"]),
                    "c": float(b["c"]),
                    "v": float(b["v"])
                })

            return clean

        except Exception:
            return []

    # ==================================================
    # CORE ANALYSIS
    # ==================================================

    def analyze_symbol(self, symbol, snapshot, wash_list):

        def fail(reason, value=None):
            if DEBUG_MODE:
                print(f"[{symbol}] ❌ {reason} -> {value}")
            return None

        latest = snapshot.get("latestTrade", {})
        daily = snapshot.get("dailyBar", {})



        price = latest.get("p", 0)
        open_price = daily.get("o", 0)
        high = daily.get("h", 0)
        low = daily.get("l", 0)
        volume = daily.get("v", 0)

        if price == 0 or open_price == 0:
            return fail("NO DATA", 0)

        if not (DISCOVERY_MIN_PRICE <= price <= MAX_PRICE):
            return fail("DISCOVERY PRICE FILTER", price)

        trade_eligible = price >= MIN_PRICE

        bars = self.get_bars(symbol, limit = 20)

        if not bars:
            return fail("NO BARS")

        df = pd.DataFrame(bars)
        print(symbol, "bars:", len(df))

        if len(df) < 3:
            return fail("Insufficient BARS", len(df))

        orb_high, orb_low = orb_levels(df)

        rvol = calculate_rvol(df)

        atr = calc_atr(df)
        print(symbol, "RVOL =", rvol)
        print(symbol, "ATR =", atr)
        ##atr = 0

        spike = volume_spike(df)

        vwap_series = calc_vwap(df)

        current_vwap = float(vwap_series.iloc[-1])

        vwap_ok = price > current_vwap

        orb_break = price > orb_high

        strong_breakout = (
                orb_break
                and vwap_ok
                and rvol >= 3
        )


        if price == 0 or open_price == 0:
            return fail("NO DATA", 0)

        # =========================
        # METRICS
        # =========================

        gain = ((price - open_price) / open_price) * 100

        premarket_candidate = False

        if gain >= 3 and rvol >= 2:
            premarket_candidate = True

        daily_range = ((high - low) / price) * 100 if price else 0

        gap_strength = gain

        hod_break = 1 if price >= high * 0.995 else 0

        vol_score = rvol_score(rvol) ##min(volume / 500_000, 5)

        # =========================
        # FILTERS
        # =========================

        #if not (DISCOVERY_MIN_PRICE <= price <= MAX_PRICE):
        #    return fail("DISCOVERY PRICE FILTER", price)

        if gain < MIN_GAIN:
            return fail("GAIN FILTER", gain)

        # =========================
        # CONTINUATION ENGINE
        # =========================

        distance_from_hod = 0

        if high > 0:
            distance_from_hod = ((high - price) / high) * 100

        upside_remaining = 0

        if price > 0:
            upside_remaining = round(((high - price) / price) * 100, 2)

        # HOD proximity score
        if distance_from_hod <= 2:
            hod_score = 30
        elif distance_from_hod <= 5:
            hod_score = 20
        elif distance_from_hod <= 10:
            hod_score = 10
        else:
            hod_score = 0

        # volume persistence
        if volume >= 1_000_000:
            continuation_volume = 30
        elif volume >= 500_000:
            continuation_volume = 20
        elif volume >= 100_000:
            continuation_volume = 10
        else:
            continuation_volume = 0

        # momentum quality
        if gain >= 20:
            momentum_score = 30
        elif gain >= 10:
            momentum_score = 20
        elif gain >= 5:
            momentum_score = 10
        else:
            momentum_score = 0

        # range expansion
        if daily_range >= 20:
            range_score = 10
        elif daily_range >= 10:
            range_score = 5
        else:
            range_score = 0

        continuation_score = (
                hod_score +
                continuation_volume +
                momentum_score +
                range_score +
                vol_score
        )

        if strong_breakout:
            continuation_score += 20

        early_signal = (
                rvol >= 3
                and price > current_vwap
                and distance_from_hod <= 3
        )

        # =========================
        # OPPORTUNITY SCORE
        # =========================

        opportunity = 0

        # Above VWAP
        if vwap_ok:
            opportunity += 20

        # Near HOD
        if distance_from_hod <= 2:
            opportunity += 20

        # RVOL Bonus
        opportunity += min(rvol * 5, 25)

        # ORB Strong Breakout
        if strong_breakout:
            opportunity += 20

        # Early Signal
        if early_signal:
            opportunity += 15

        opportunity = round(opportunity, 2)

        # =========================
        # CONTINUATION GRADE
        # =========================

        if continuation_score >= 80:
            continuation_grade = "A+"
        elif continuation_score >= 65:
            continuation_grade = "A"
        elif continuation_score >= 50:
            continuation_grade = "B"
        elif continuation_score >= 35:
            continuation_grade = "C"
        else:
            continuation_grade = "F"

        raw_score = round(
            (
                    gain * 1.0 +
                    daily_range * 0.5 +
                    vol_score * 1.5 +
                    continuation_score
            ),
            2
        )
        score = round(max(0, min(raw_score, 100)), 2)
        if DEBUG_MODE:
            print(
                symbol,
                "gain=", round(gain, 2),
                "range=", round(daily_range, 2),
                "vol=", volume,
                "score=", score
            )

        if score < MIN_SCORE:
            return fail("SCORE FILTER", score)

        # =========================
        # SETUP LOGIC
        # =========================

        setup = []

        if gain > 5:
            setup.append("GAP")

        if distance_from_hod <= 2:
            setup.append("HOD")

        if vol_score > 1:
            setup.append("VOL")

        setup_label = "+".join(setup) if setup else "NONE"

        # =========================
        # STATE CLASSIFICATION
        # =========================

        state = "DEAD"

        if continuation_score >= 80 and distance_from_hod <= 2:
            state = "🟢 HOD ATTACK"

        elif (
                gain >= 15
                and price > current_vwap
                and continuation_score >= 70
                and upside_remaining >= 5
        ):
            state = "🚀 TREND LEADER"

        elif orb_break:
            state = "🟢 ORB BREAKOUT"

        elif (

                rvol >= 3

                and distance_from_hod <= 3

                and price > current_vwap

                and not orb_break

        ):

            state = "🔵 LAUNCH PAD"

        elif (

                price > current_vwap

                and rvol >= 2

                and distance_from_hod <= 10

                and not orb_break

        ):

            state = "🟣 ENTRY ALERT"

        elif current_vwap > 0 and price > current_vwap:
            state = "🔷 VWAP RECLAIM"

        elif gain > 5:
            state = "🟡 PULLBACK"

        elif distance_from_hod > 10:
            state = "🟠 EXTENDED"

        else:
            state = "🔴 DEAD"

        # =========================
        # LIFECYCLE CLASSIFICATION
        # =========================

        lifecycle = "⚫ DORMANT"
        lifecycle_rank = 0
        action = "IGNORE"

        vwap_extension = 0

        if current_vwap > 0:
            vwap_extension = (
                                     (price - current_vwap)
                                     / current_vwap
                             ) * 100

        # Stage 9 — Failed / Exit Zone
        if (
                price < current_vwap
                and gain > 5
                and distance_from_hod > 10
        ):
            lifecycle = "🔴 EXIT ZONE"
            lifecycle_rank = 9
            action = "AVOID / EXIT"

        # Stage 8 — Extended
        elif (
                vwap_extension >= 8
                or (
                        gain >= 25
                        and distance_from_hod <= 2
                )
        ):
            lifecycle = "🟠 EXTENDED"
            lifecycle_rank = 8
            action = "Wait"

        # Stage 7 — Trend Leader
        elif (
                gain >= 15
                and price > current_vwap
                and continuation_score >= 70
                and rvol >= 2
        ):
            lifecycle = "🚀 TREND LEADER"
            lifecycle_rank = 7
            action = "Hold"

        # Stage 6 — HOD Attack
        elif (
                continuation_score >= 80
                and distance_from_hod <= 2
        ):
            lifecycle = "🟢 HOD ATTACK"
            lifecycle_rank = 6
            action = "Add"

        # Stage 5 — ORB Confirmed
        elif (
                strong_breakout
        ):
            lifecycle = "✅ ORB Confirmed"
            lifecycle_rank = 5
            action = "BUY"

        # Stage 4 — Entry Alert
        elif (
                price > current_vwap
                and rvol >= 2
                and distance_from_hod <= 10
                and not orb_break
                and vwap_extension <= 6
        ):
            lifecycle = "🟣 Entry Alert"
            lifecycle_rank = 4
            action = "Buy"

        # Stage 3 — Launch Pad
        elif (
                price > current_vwap
                and rvol >= 1.5
                and distance_from_hod <= 5
                and not orb_break
        ):
            lifecycle = "🔵 Launch Pad"
            lifecycle_rank = 3
            action = "PREPARE"

        # Stage 2 — Momentum Building
        elif (
                price > current_vwap
                and rvol >= 1
                and gain >= 3
        ):
            lifecycle = "🟡 Momentum"
            lifecycle_rank = 2
            action = "Prepare"

        # Stage 1 — Discovery
        elif (
                gain >= 3
                or volume >= 100_000
        ):
            lifecycle = "⚪ Discovery"
            lifecycle_rank = 1
            action = "Watch"

        # =========================
        # TRADE PLAN
        # =========================

        risk = price * 0.02

        plan = {
            "entry": round(price, 2),
            "stop": round(price - risk, 2),
            "t1": round(price + risk, 2),
            "t2": round(price + risk * 2, 2),
            "t3": round(price + risk * 3, 2)
        }

        # =========================
        # ORB STATUS
        # =========================

        orb_status = "UNKNOWN"

        if price > orb_high:
            orb_status = "ORB BREAKOUT"

        elif price >= (orb_high * 0.98):
            orb_status = "LOADING"

        elif price > orb_low:
            orb_status = "INSIDE ORB"

        else:
            orb_status = "FAILED"

        # =========================
        # WASH SALE STATUS
        # =========================

        wash_status = "CLEAR"
        wash_days = 0

        if symbol in wash_list:
            wash_status = "⚠️ WASH RISK"

            wash_days = wash_list[symbol]["days_remaining"]

        if state == "🚀 TREND LEADER":
            print(
                f"TREND LEADER: {symbol} | "
                f"Gain={gain:.1f}% | "
                f"RVOL={rvol:.1f} | "
                f"Upside={upside_remaining:.1f}%"
            )

        return {
            "Symbol": symbol,
            #"State": state,
            "Grade": grade_score(score),
            "TradeEligible": "YES" if trade_eligible else "WATCH",
            "ContGrade": continuation_grade,
            "Upside%": upside_remaining,
            "Lifecycle": lifecycle,
            "LifecycleRank": lifecycle_rank,
            "Action": action,
            "VWAP_Ext%": round(vwap_extension, 2),

            #"WashStatus": wash_status,
            #"WashDays": wash_days,

            "Price": round(price, 2),
            "Gain%": round(gain, 2),
            "Score": score,
            "Continuation": continuation_score,
            "Opportunity": opportunity,
            "RVOL": round(rvol, 2),
            "ATR": round(atr, 3),
            "VWAP": round(current_vwap, 2),

            "State": state,
            "ORB": orb_status,
            "ORB_High": round(orb_high, 2),
            "ORB_Low": round(orb_low, 2),
            "ORB_Break": (
                "STRONG"
                if strong_breakout
                else "YES"
                if orb_break
                else ""
            ),

            "Premarket": "YES" if premarket_candidate else "",
            "EarlySignal": "YES" if early_signal else "",

            "HOD_Dist%": round(distance_from_hod, 2),
            "Setup": setup_label,

            "Entry": plan["entry"],
            "Stop": plan["stop"],
            "T1": plan["t1"],
            "T2": plan["t2"],
            "T3": plan["t3"]
        }

    # ==================================================
    # SCAN LOOP
    # ==================================================

    def run_scan(self, mode="watchlist"):

        if mode == "watchlist":
            symbols = WATCHLIST

        elif mode == "movers":
            symbols = self.get_movers()


        elif mode == "combined":

            movers = self.get_movers()

            symbols = list(dict.fromkeys(WATCHLIST + movers))

            if DEBUG_MODE:
                print("\n==============================")

                print("SCAN MODE: COMBINED")

                print("WATCHLIST COUNT:", len(WATCHLIST))

                print("MOVERS COUNT:", len(movers))

                print("MOVERS:", movers)

                print("TOTAL UNIQUE COUNT:", len(symbols))

                print("ALL SYMBOLS:", symbols)

                print("==============================\n")

        else:
            return pd.DataFrame()

        snapshots = self.get_snapshot(symbols)
        wash_list = self.trade_journal.get_wash_sale_symbols()

        results = []

        for symbol in symbols:

            try:
                snapshot = snapshots.get(symbol, {})
                row = self.analyze_symbol(symbol, snapshot, wash_list)

                if row:
                    results.append(row)

            except Exception as e:
                if DEBUG_MODE:
                    print(symbol, "error:", e)

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        # Dashboard safety
        for col in ["Grade", "ContGrade", "Setup", "State", "Lifecycle", "LifecycleRank", "Action", "VWAP_Ext%","ORB", "WashStatus", "WashDays"]:
            if col not in df.columns:
                df[col] = ""

        # Continuation ranking
        grade_rank = {
            "A+": 5,
            "A": 4,
            "B": 3,
            "C": 2,
            "F": 1
        }

        df["ContRank"] = df["ContGrade"].map(grade_rank)

        #return (
        #    df.sort_values(
        #        ["Opportunity", "Score"],
        #        ascending=False
        #    )
        #    .drop(columns=["ContRank"])
        #)

        state_rank = {
            "🟢 HOD ATTACK": 8,
            "🚀 TREND LEADER": 7,
            "🟢 ORB BREAKOUT": 6,
            "🟣 ENTRY ALERT": 5,
            "🔵 LAUNCH PAD": 4,
            "🔷 VWAP RECLAIM": 3,
            "🟡 PULLBACK": 2,
            "🟠 EXTENDED": 1,
            "🔴 DEAD": 0
        }

        orb_rank = {
            "ORB BREAKOUT": 4,
            "LOADING": 3,
            "INSIDE ORB": 2,
            "FAILED": 1
        }

        print(df[["Symbol", "State", "ORB", "ContGrade"]])
        df["StateRank"] = df["State"].map(state_rank)
        df["ORBRank"] = df["ORB"].map(orb_rank)

        return (
            df.sort_values(
                [
                    "LifecycleRank",
                    "Continuation",
                    "Opportunity",
                    "Score"
                ],
                ascending=False
            )
            .drop(
                columns=[
                    "StateRank",
                    "ORBRank"
                ],
                errors="ignore"
            )
        )


# optional CLI test
if __name__ == "__main__":

    scanner = KaizenScanner()

    df = scanner.run_scan("combined")

    print(df.to_string(index=False))