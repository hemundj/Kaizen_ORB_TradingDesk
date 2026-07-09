import requests
import pandas as pd

from config import (
    API_KEY,
    SECRET_KEY,
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

    # ==================================================
    # DATA
    # ==================================================

    def get_movers(self):

        url = f"{self.base_url}/v1beta1/screener/stocks/movers"

        try:
            r = requests.get(url, headers=self.headers, params={"top": 50}, timeout=15)

            if r.status_code != 200:
                return []

            gainers = r.json().get("gainers", [])
            clean_symbols = []

            for g in gainers:

                symbol = g.get("symbol", "")

                if (
                        "." in symbol
                        or symbol.endswith("W")
                        or symbol.endswith("R")
                        or symbol.endswith("U")
                ):
                    continue

                clean_symbols.append(symbol)

            return clean_symbols

        except Exception:
            return []

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

        if not (MIN_PRICE <= price <= MAX_PRICE):
            return fail("PRICE FILTER", price)

        bars = self.get_bars(symbol, limit = 20)

        if not bars:
            return fail("NO BARS")

        df = pd.DataFrame(bars)
        print(symbol, "bars:", len(df))

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

        orb_break = (
                price > orb_high
                and vwap_ok
                and rvol >= 2
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

        if not (MIN_PRICE <= price <= MAX_PRICE):
            return fail("PRICE FILTER", price)

        if gain < MIN_GAIN:
            return fail("GAIN FILTER", gain)

        # =========================
        # CONTINUATION ENGINE
        # =========================

        distance_from_hod = 0

        if high > 0:
            distance_from_hod = ((high - price) / high) * 100

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

        if orb_break:
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

        # ORB Break
        if orb_break:
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

        elif orb_break:
            state = "🟢 ORB BREAKOUT"

        elif (
                rvol >= 3
                and distance_from_hod <= 3
                and price > current_vwap
        ):
            state = "🔵 LAUNCH PAD"

        elif current_vwap > 0 and price > current_vwap:
            state = "🔷 VWAP RECLAIM"

        elif gain > 5:
            state = "🟡 PULLBACK"

        elif distance_from_hod > 10:
            state = "🟠 EXTENDED"

        else:
            state = "🔴 DEAD"

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

        return {
            "Symbol": symbol,
            #"State": state,
            "Grade": grade_score(score),
            "ContGrade": continuation_grade,

            "WashStatus": wash_status,
            "WashDays": wash_days,

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
            "ORB_Break": "YES" if orb_break else "",

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
            symbols = list(set(WATCHLIST + self.get_movers()))

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
        for col in ["Grade", "ContGrade", "Setup", "State", "ORB", "WashStatus", "WashDays"]:
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
            "🟢 HOD ATTACK": 7,
            "🟢 ORB BREAKOUT": 6,
            "🔵 LAUNCH PAD": 5,
            "🔷 VWAP RECLAIM": 4,
            "🟡 PULLBACK": 3,
            "🟠 EXTENDED": 2,
            "🔴 DEAD": 1
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
                ["StateRank", "ORBRank", "Continuation", "Score"],
                ascending=False
            )
            .drop(columns=["StateRank", "ORBRank"])
        )


# optional CLI test
if __name__ == "__main__":

    scanner = KaizenScanner()

    df = scanner.run_scan("combined")

    print(df.to_string(index=False))