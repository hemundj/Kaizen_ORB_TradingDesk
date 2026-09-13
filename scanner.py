import requests
import pandas as pd
import csv
import os

from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

from config import (
    API_KEY,
    SECRET_KEY,
    DISCOVERY_MIN_PRICE,
    MIN_PRICE,
    MAX_PRICE,
    MIN_GAIN,
    MIN_SCORE,
    DEBUG_MODE,
    ENABLE_TRUE_RVOL,
)

from fundamentals import FundamentalsEngine
from watchlist import WATCHLIST
from grading import grade_score
from indicators import (
    calc_atr,
    calc_vwap,
    orb_levels,
    volume_spike,
    calculate_volume_ratio,
    calculate_float_turnover,
    calculate_intraday_rvol,
    rvol_score,
    near_hod
)

from trade_journal import TradeJournal

class KaizenScanner:

    def log_alert_path_audit(
            self,
            symbol,
            price,
            gain,
            rvol,
            current_vwap,
            vwap_ok,
            vwap_extension,
            high,
            distance_from_hod,
            upside_remaining,
            orb_high,
            orb_break,
            strong_breakout,
            early_signal,
            continuation_score,
            score,
            state,
            lifecycle,
            action,
            momentum_ignition,
            ignition_reason,
            alert_eligible,
            alert_blocked_reason
    ):

        filename = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "alert_path_audit.csv"
        )

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
                    "Price",
                    "GainPercent",
                    "RVOL",
                    "VWAP",
                    "AboveVWAP",
                    "VWAP_ExtPercent",
                    "HOD",
                    "HOD_DistPercent",
                    "UpsideRemainingPercent",
                    "ORB_High",
                    "ORB_Break",
                    "StrongBreakout",
                    "EarlySignal",
                    "Continuation",
                    "Score",
                    "State",
                    "Lifecycle",
                    "Action",
                    "MomentumIgnition",
                    "IgnitionReason",
                    "AlertEligible",
                    "BlockedReason"
                ])

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                round(price, 4),
                round(gain, 2),
                round(rvol, 2),
                round(current_vwap, 4),
                vwap_ok,
                round(vwap_extension, 2),
                round(high, 4),
                round(distance_from_hod, 2),
                round(upside_remaining, 2),
                round(orb_high, 4),
                orb_break,
                strong_breakout,
                early_signal,
                continuation_score,
                round(score, 2),
                state,
                lifecycle,
                action,
                momentum_ignition,
                ignition_reason,
                alert_eligible,
                alert_blocked_reason
            ])


    def __init__(self):

        self.headers = {
            "APCA-API-KEY-ID": API_KEY.strip(),
            "APCA-API-SECRET-KEY": SECRET_KEY.strip()
        }

        self.base_url = "https://data.alpaca.markets"
        self.trade_journal = TradeJournal()
        self.fundamentals = FundamentalsEngine()

        # Track the previous mover list so we can detect entries and exits
        self.previous_movers = set()
        self.discovery_seen_date = datetime.now().date()
        self.movers_initialized = False

        # Momentum Ignition memory.  This lets Kaizen remember when a ticker
        # leaves the Alpaca mover list and then re-enters at a higher price /
        # better rank.  That re-entry behavior can be an early momentum clue.
        self.mover_history = {}

        # ==================================================
        # MANUAL / TOS RADAR
        # ==================================================

        # Symbols manually added from TOS Radar or another
        # external discovery source.
        #
        # These remain active until manually removed or
        # Kaizen is closed.
        self.manual_symbols = set()

    # ==================================================
    # MANUAL RADAR
    # ==================================================

    def add_manual_symbol(
            self,
            symbol,
            source="MANUAL_TOS"
    ):
        symbol = str(symbol).strip().upper()

        if not symbol:
            return False

        # Basic symbol validation
        if not symbol.replace("-", "").isalnum():
            print(
                f"MANUAL RADAR: Invalid symbol '{symbol}'"
            )
            return False

        # Already being manually monitored
        if symbol in self.manual_symbols:
            print(
                f"MANUAL RADAR: {symbol} already active"
            )
            return False

        self.manual_symbols.add(symbol)

        self.log_manual_discovery(
            symbol=symbol,
            event="ENTRY",
            source=source
        )

        print(
            f"\nMANUAL RADAR ADDED: {symbol}"
            f" | Source={source}"
        )

        return True

    def remove_manual_symbol(
            self,
            symbol,
            source="MANUAL_TOS"
    ):
        symbol = str(symbol).strip().upper()

        if symbol not in self.manual_symbols:
            return False

        self.manual_symbols.remove(symbol)

        self.log_manual_discovery(
            symbol=symbol,
            event="EXIT",
            source=source
        )

        print(
            f"\nMANUAL RADAR REMOVED: {symbol}"
        )

        return True

    def get_manual_symbols(self):

        return sorted(self.manual_symbols)

    def log_manual_discovery(
            self,
            symbol,
            event,
            source="MANUAL_TOS"
    ):

        filename = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "discovery_events.csv"
        )

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
                        "Event",
                        "Rank",
                        "MoverPrice",
                        "Change",
                        "PercentChange",
                        "Source"
                    ])

                writer.writerow([
                    timestamp,
                    symbol,
                    event,
                    "",
                    "",
                    "",
                    "",
                    source
                ])

        except Exception as e:

            print(
                "MANUAL DISCOVERY LOG ERROR:",
                type(e).__name__,
                e
            )

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

        # Update Momentum Ignition context before writing the discovery log.
        # A symbol that re-enters the mover list after previously appearing can
        # carry useful information even if its RVOL proxy is still below 2.0.
        for symbol in current_movers:
            mover = mover_lookup.get(symbol, {})
            current_rank = mover.get("rank", 0) or 0
            current_price = mover.get("price", 0) or 0

            try:
                current_rank = int(current_rank)
            except (TypeError, ValueError):
                current_rank = 0

            try:
                current_price = float(current_price)
            except (TypeError, ValueError):
                current_price = 0

            history = self.mover_history.setdefault(symbol, {
                "last_entry_price": 0.0,
                "last_entry_rank": 0,
                "reentry_count": 0,
                "reentered_recently": False,
                "entry_price_change_pct": 0.0,
                "rank_improvement": 0,
                "ignition_timestamp": None,
            })

            # Only calculate re-entry acceleration when the symbol has newly
            # returned to the mover list.
            if symbol in entered_symbols:
                previous_entry_price = history.get("last_entry_price", 0) or 0
                previous_entry_rank = history.get("last_entry_rank", 0) or 0

                is_reentry = previous_entry_price > 0

                if is_reentry:
                    history["reentry_count"] += 1
                    history["reentered_recently"] = True
                    history["ignition_timestamp"] = datetime.now()

                    if current_price > 0 and previous_entry_price > 0:
                        history["entry_price_change_pct"] = round(
                            ((current_price - previous_entry_price)
                             / previous_entry_price) * 100,
                            2
                        )

                    if current_rank > 0 and previous_entry_rank > 0:
                        # Positive = improved toward rank #1.
                        history["rank_improvement"] = (
                            previous_entry_rank - current_rank
                        )
                else:
                    history["reentered_recently"] = False
                    history["entry_price_change_pct"] = 0.0
                    history["rank_improvement"] = 0

                history["last_entry_price"] = current_price
                history["last_entry_rank"] = current_rank

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

    def get_daily_bars(
            self,
            symbol,
            limit=20
    ):

        url = (
            f"{self.base_url}"
            f"/v2/stocks/{symbol}/bars"
        )

        params = {
            "timeframe": "1Day",
            "limit": limit,
            "feed": "iex"
        }

        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=15
            )

            if response.status_code != 200:
                return []

            return response.json().get("bars", [])

        except Exception as error:
            if DEBUG_MODE:
                print(
                    symbol,
                    "DAILY BAR ERROR:",
                    error
                )

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

        float_shares = 0
        shares_outstanding = 0
        market_cap = 0
        free_float_pct = 0
        float_turnover = 0

#        fundamentals = (self.fundamentals.get_symbol_fundamentals(symbol))

#        float_shares = fundamentals.get( "Float", 0)

 #       shares_outstanding = fundamentals.get("SharesOutstanding", 0)

  #      market_cap = fundamentals.get("MarketCap", 0)

   #     free_float_pct = fundamentals.get( "FreeFloatPct", 0)

    #    float_turnover = calculate_float_turnover(
    #        volume,
    #        float_shares
    #    )

        bars = self.get_bars(symbol, limit = 20)
        #daily_bars = self.get_daily_bars(symbol, limit=20)

        #central_now = datetime.now(
        #    ZoneInfo("America/Chicago")
        #)

        #market_open = central_now.replace(
        #    hour=8,
        #    minute=30,
        #    second=0,
        #    microsecond=0
        #)

        #market_close = central_now.replace(
        #    hour=15,
        #    minute=0,
        #    second=0,
        #    microsecond=0
        #)

        #session_seconds = (
        #        market_close - market_open
        #).total_seconds()

        #elapsed_seconds = (
         #       central_now - market_open
        #).total_seconds()

        #elapsed_market_fraction = max(
        #    0.01,
        #    min(
        #        elapsed_seconds / session_seconds,
        #        1.0
        #    )
        #)

       #average_daily_volume = 0

        #if daily_bars:

        #    completed_daily_volumes = [
        #        float(bar.get("v", 0))
        #        for bar in daily_bars[:-1]
        #        if float(bar.get("v", 0)) > 0
        #    ]

            #if completed_daily_volumes:
            #    average_daily_volume = (
            #            sum(completed_daily_volumes)
            #            / len(completed_daily_volumes)
            #    )

        if not bars:
            return fail("NO BARS")

        df = pd.DataFrame(bars)
        print(symbol, "bars:", len(df))

        if len(df) < 3:
            return fail("Insufficient BARS", len(df))

        average_daily_volume = 0
        elapsed_market_fraction = 0

        if ENABLE_TRUE_RVOL:

            daily_bars = self.get_daily_bars(
                symbol,
                limit=20
            )

            central_now = datetime.now(
                ZoneInfo("America/Chicago")
            )

            market_open = central_now.replace(
                hour=8,
                minute=30,
                second=0,
                microsecond=0
            )

            market_close = central_now.replace(
                hour=15,
                minute=0,
                second=0,
                microsecond=0
            )

            session_seconds = (
                    market_close - market_open
            ).total_seconds()

            elapsed_seconds = (
                    central_now - market_open
            ).total_seconds()

            elapsed_market_fraction = max(
                0.01,
                min(
                    elapsed_seconds / session_seconds,
                    1.0
                )
            )

            if daily_bars:

                completed_daily_volumes = [
                    float(bar.get("v", 0))
                    for bar in daily_bars[:-1]
                    if float(bar.get("v", 0)) > 0
                ]

                if completed_daily_volumes:
                    average_daily_volume = (
                            sum(completed_daily_volumes)
                            / len(completed_daily_volumes)
                    )

        orb_high, orb_low = orb_levels(df)

        volume_ratio = calculate_volume_ratio(df)

        # Temporary compatibility until true intraday RVOL
        # receives historical average-volume data
        rvol = volume_ratio

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
        # MOMENTUM IGNITION
        # =========================

        # VWAP extension is calculated here (rather than only in Lifecycle) so
        # Momentum Ignition can avoid flagging names that are already too far
        # extended from VWAP.
        vwap_extension = 0

        if current_vwap > 0:
            vwap_extension = (
                ((price - current_vwap) / current_vwap) * 100
            )

        mover_context = self.mover_history.get(symbol, {})

        mover_reentry = bool(
            mover_context.get("reentered_recently", False)
        )
        mover_price_accel = float(
            mover_context.get("entry_price_change_pct", 0) or 0
        )
        mover_rank_improvement = int(
            mover_context.get("rank_improvement", 0) or 0
        )

        # Re-entry signals are considered fresh for ten minutes.  This keeps an
        # old mover-list event from influencing the stock for the entire day.
        ignition_timestamp = mover_context.get("ignition_timestamp")
        mover_reentry_fresh = False

        if mover_reentry and ignition_timestamp is not None:
            ignition_age_seconds = (
                datetime.now() - ignition_timestamp
            ).total_seconds()
            mover_reentry_fresh = 0 <= ignition_age_seconds <= 600

        # EMAT-style exception: strong price/range/continuation behavior should
        # not be ignored just because the temporary RVOL proxy prints 1.92
        # instead of 2.00.
        momentum_exception = (
            gain >= 15
            and daily_range >= 15
            and rvol >= 1.5
            and continuation_score >= 50
            and score >= 80
            and vwap_ok
            and vwap_extension <= 8
        )

        # Alpaca mover re-entry / acceleration path.  Example: a ticker exits
        # the top-50 list and re-enters at a materially higher price and/or much
        # better rank.
        mover_acceleration = (
            mover_reentry_fresh
            and vwap_ok
            and gain >= 5
            and rvol >= 1.25
            and vwap_extension <= 8
            and (
                mover_price_accel >= 5
                or mover_rank_improvement >= 8
            )
        )

        # General technical ignition path.  This is an EARLY WARNING, not an
        # automatic buy signal.
        technical_ignition = (
            vwap_ok
            and gain >= 8
            and rvol >= 1.5
            and continuation_score >= 40
            and distance_from_hod <= 8
            and vwap_extension <= 8
            and (
                spike
                or momentum_exception
            )
        )

        momentum_ignition = (
            momentum_exception
            or mover_acceleration
            or technical_ignition
        )

        ignition_reasons = []

        if momentum_exception:
            ignition_reasons.append("STRONG_MOMENTUM")

        if mover_acceleration:
            ignition_reasons.append("MOVER_REENTRY")

        if technical_ignition and spike:
            ignition_reasons.append("VOLUME_ACCEL")

        ignition_reason = "+".join(ignition_reasons)

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

        # Highest priority:
        # Stock is actively attacking the High of Day
        if continuation_score >= 80 and distance_from_hod <= 2:
            state = "🟢 HOD ATTACK"

        # Sudden momentum / volume acceleration
        # Must take priority over Trend Leader so an active ignition
        # event is not hidden by the broader Trend Leader classification.
        elif momentum_ignition:
            state = "⚡ MOMENTUM IGNITION"

        # Confirmed ORB breakout
        elif strong_breakout:
            state = "🟢 ORB BREAKOUT"

        # Established momentum leader
        elif (
                gain >= 15
                and price > current_vwap
                and continuation_score >= 70
                and upside_remaining >= 5
        ):
            state = "🚀 TREND LEADER"

        # High-RVOL stock approaching HOD but not yet breaking ORB
        elif (
                rvol >= 3
                and distance_from_hod <= 3
                and price > current_vwap
                and not orb_break
        ):
            state = "🔵 LAUNCH PAD"

        # Potential entry setup
        elif (
                price > current_vwap
                and rvol >= 2
                and distance_from_hod <= 10
                and not orb_break
        ):
            state = "🟣 ENTRY ALERT"

        # Above VWAP but no stronger setup yet
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

        # Stage 10 — Failed / Exit Zone
        if (
                price < current_vwap
                and gain > 5
                and distance_from_hod > 10
        ):
            lifecycle = "🔴 EXIT ZONE"
            lifecycle_rank = 10
            action = "AVOID / EXIT"

        # Stage 9 — Extended
        elif (
                vwap_extension >= 8
                or (
                        gain >= 25
                        and distance_from_hod <= 2
                )
        ):
            lifecycle = "🟠 EXTENDED"
            lifecycle_rank = 9
            action = "Wait"

        # Stage 8 — Trend Leader
        elif (
                gain >= 15
                and price > current_vwap
                and continuation_score >= 70
                and rvol >= 2
        ):
            lifecycle = "🚀 TREND LEADER"
            lifecycle_rank = 8
            action = "Hold"

        # Stage 7 — HOD Attack
        elif (
                continuation_score >= 80
                and distance_from_hod <= 2
        ):
            lifecycle = "🟢 HOD ATTACK"
            lifecycle_rank = 7
            action = "Add"

        # Stage 6 — ORB Confirmed
        elif strong_breakout:
            lifecycle = "✅ ORB Confirmed"
            lifecycle_rank = 6
            action = "BUY"

        # Stage 5 — Entry Alert
        elif (
                price > current_vwap
                and rvol >= 2
                and distance_from_hod <= 10
                and not orb_break
                and vwap_extension <= 6
        ):
            lifecycle = "🟣 Entry Alert"
            lifecycle_rank = 5
            action = "Buy"

        # Stage 4 — Momentum Ignition
        elif momentum_ignition:
            lifecycle = "⚡ MOMENTUM IGNITION"
            lifecycle_rank = 4
            action = "WATCH NOW"

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

        # ============================================================
        # ALERT PATH AUDIT
        # Automatically inspect strong stocks that Kaizen has NOT
        # promoted into an actionable alert state.
        # ============================================================

        alerted_state = (
                "ENTRY ALERT" in state
                or "ORB BREAKOUT" in state
                or "HOD ATTACK" in state
                or "MOMENTUM IGNITION" in state
        )

        audit_candidate = (
                score >= 75
                or momentum_ignition
                or strong_breakout
                or rvol >= 2
                or gain >= 10
        )

        # =========================
        # ALERT ELIGIBILITY AUDIT
        # Diagnostic only
        # =========================

        alert_states = {
            "🟣 ENTRY ALERT",
            "🟢 ORB BREAKOUT",
            "🟢 HOD ATTACK",
            "⚡ MOMENTUM IGNITION",
        }

        alert_eligible = state in alert_states

        blocked_reasons = []

        if current_vwap > 0 and price <= current_vwap:
            blocked_reasons.append("BELOW_VWAP")

        if rvol < 2:
            blocked_reasons.append("LOW_RVOL")

        if score < 75:
            blocked_reasons.append("LOW_SCORE")

        if gain < 0:
            blocked_reasons.append("NEGATIVE_GAIN")

        if distance_from_hod > 10:
            blocked_reasons.append("FAR_FROM_HOD")

        if vwap_extension >= 8:
            blocked_reasons.append("VWAP_EXTENDED")

        if state not in alert_states:
            blocked_reasons.append("NO_ALERT_STATE")

        alert_blocked_reason = (
            "+".join(blocked_reasons)
            if blocked_reasons
            else ""
        )

        if DEBUG_MODE and audit_candidate:
            print(
                "\n===== ALERT PATH AUDIT ====="
                f"\nSymbol: {symbol}"
                f"\nPrice: {price:.4f}"
                f"\nGain: {gain:.2f}%"
                f"\nRVOL: {rvol:.2f}"
                f"\nVWAP: {current_vwap:.4f}"
                f"\nAbove VWAP: {vwap_ok}"
                f"\nVWAP Extension: {vwap_extension:.2f}%"
                f"\nHOD: {high:.4f}"
                f"\nDistance From HOD: {distance_from_hod:.2f}%"
                f"\nUpside Remaining: {upside_remaining:.2f}%"
                f"\nORB High: {orb_high:.4f}"
                f"\nORB Break: {orb_break}"
                f"\nStrong Breakout: {strong_breakout}"
                f"\nEarly Signal: {early_signal}"
                f"\nContinuation: {continuation_score}"
                f"\nScore: {score}"
                f"\nState: {state}"
                f"\nLifecycle: {lifecycle}"
                f"\nAction: {action}"
                f"\nMomentum Ignition: {momentum_ignition}"
                f"\nIgnition Reason: {ignition_reason}"
                "\n============================\n"
            )

            self.log_alert_path_audit(
                symbol=symbol,
                price=price,
                gain=gain,
                rvol=rvol,
                current_vwap=current_vwap,
                vwap_ok=vwap_ok,
                vwap_extension=vwap_extension,
                high=high,
                distance_from_hod=distance_from_hod,
                upside_remaining=upside_remaining,
                orb_high=orb_high,
                orb_break=orb_break,
                strong_breakout=strong_breakout,
                early_signal=early_signal,
                continuation_score=continuation_score,
                score=score,
                state=state,
                lifecycle=lifecycle,
                action=action,
                momentum_ignition=momentum_ignition,
                ignition_reason=ignition_reason,
                alert_eligible=alert_eligible,
                alert_blocked_reason=alert_blocked_reason
            )

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

        if strong_breakout:
            orb_status = "ORB CONFIRMED"

        elif orb_break:
            orb_status = "ORB DETECTED"

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

        if state == "⚡ MOMENTUM IGNITION":
            print(
                f"MOMENTUM IGNITION: {symbol} | "
                f"Gain={gain:.1f}% | "
                f"RVOL={rvol:.1f} | "
                f"Continuation={continuation_score} | "
                f"Reason={ignition_reason}"
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
            "Float": float_shares,
            "FloatTurnover%": round(float_turnover, 2),
            "SharesOutstanding": shares_outstanding,
            "MarketCap": market_cap,
            "VolumeRatio": round(volume_ratio, 2),
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
            "MomentumIgnition": "YES" if momentum_ignition else "",
            "IgnitionReason": ignition_reason,
            "MoverReentry": "YES" if mover_reentry_fresh else "",
            "MoverPriceAccel%": round(mover_price_accel, 2),
            "MoverRankImprovement": mover_rank_improvement,

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

        manual_symbols = self.get_manual_symbols()

        if mode == "watchlist":

            symbols = list(
                dict.fromkeys(
                    WATCHLIST
                    + manual_symbols
                )
            )

        elif mode == "movers":

            movers = self.get_movers()

            symbols = list(
                dict.fromkeys(
                    movers
                    + manual_symbols
                )
            )

        elif mode == "combined":

            movers = self.get_movers()

            symbols = list(
                dict.fromkeys(
                    WATCHLIST
                    + movers
                    + manual_symbols
                )
            )

            if DEBUG_MODE:
                print("\n==============================")

                print("SCAN MODE: COMBINED")

                print(
                    "WATCHLIST COUNT:",
                    len(WATCHLIST)
                )

                print(
                    "MOVERS COUNT:",
                    len(movers)
                )

                print(
                    "MANUAL RADAR COUNT:",
                    len(manual_symbols)
                )

                print(
                    "MANUAL RADAR:",
                    manual_symbols
                )

                print(
                    "MOVERS:",
                    movers
                )

                print(
                    "TOTAL UNIQUE COUNT:",
                    len(symbols)
                )

                print(
                    "ALL SYMBOLS:",
                    symbols
                )

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
            "🟢 HOD ATTACK": 9,
            "🚀 TREND LEADER": 8,
            "🟢 ORB BREAKOUT": 7,
            "🟣 ENTRY ALERT": 6,
            "⚡ MOMENTUM IGNITION": 5,
            "🔵 LAUNCH PAD": 4,
            "🔷 VWAP RECLAIM": 3,
            "🟡 PULLBACK": 2,
            "🟠 EXTENDED": 1,
            "🔴 DEAD": 0
        }

        orb_rank = {
            "ORB CONFIRMED": 5,
            "ORB DETECTED": 4,
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