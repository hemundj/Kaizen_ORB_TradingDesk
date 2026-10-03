"""Provider-independent Market Radar engine for Kaizen Phase 3.

MarketRadar receives normalized observations. It owns intraday memory, mover
entry/re-entry state, scan-to-scan acceleration, cumulative-volume acceleration,
radar scoring, lifecycle classification, and transition events. It intentionally
contains no Alpaca/Massive/vendor API code.
"""
from datetime import datetime


class MarketRadar:
    STATES = ("TRACKING", "ACCELERATING", "IGNITION", "ACTIVE", "EXTENDED", "COOLING")

    def __init__(self):
        self.symbols = {}
        self.current_universe = set()
        self.session_date = datetime.now().date()
        self.events = []

    @staticmethod
    def _float(value, default=0.0):
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _int(value, default=0):
        try:
            return int(value or default)
        except (TypeError, ValueError):
            return default

    def reset_daily(self, force=False):
        today = datetime.now().date()
        if force or today != self.session_date:
            self.symbols.clear()
            self.current_universe.clear()
            self.events.clear()
            self.session_date = today

    def _new_record(self, symbol, source):
        return {
            "symbol": symbol, "source": source, "first_seen": None, "last_seen": None,
            "observation_count": 0, "consecutive_scans": 0, "present": False,
            "current_price": 0.0, "previous_price": 0.0, "current_rank": 0, "previous_rank": 0,
            "current_percent_change": 0.0, "previous_percent_change": 0.0,
            "price_accel_pct": 0.0, "rank_accel": 0, "percent_change_accel": 0.0,
            "last_entry_price": 0.0, "last_entry_rank": 0, "reentry_count": 0,
            "reentered_recently": False, "entry_price_change_pct": 0.0, "rank_improvement": 0,
            "ignition_timestamp": None,
            "current_volume": 0.0, "previous_volume": 0.0, "volume_delta": 0.0,
            "previous_volume_delta": 0.0, "volume_accel_ratio": 0.0,
            "rvol": 0.0, "above_vwap": False, "vwap_extension": 0.0, "hod_distance": 999.0,
            "gain": 0.0, "radar_score": 0.0, "radar_reason": "", "radar_state": "TRACKING",
            "previous_radar_state": "", "last_state_change": None,
        }

    def observe_batch(self, observations):
        """Consume one provider universe snapshot and return entered/exited sets."""
        self.reset_daily()
        now = datetime.now()
        normalized = {str(o.get("symbol", "")).upper(): o for o in observations if o.get("symbol")}
        current = set(normalized)
        entered = current - self.current_universe
        exited = self.current_universe - current

        for symbol in exited:
            rec = self.symbols.get(symbol)
            if rec:
                rec["present"] = False
                rec["consecutive_scans"] = 0
                rec["reentered_recently"] = False
                rec["last_seen"] = now

        for symbol, obs in normalized.items():
            source = obs.get("source", "UNKNOWN")
            rec = self.symbols.setdefault(symbol, self._new_record(symbol, source))
            rec["source"] = source
            price = self._float(obs.get("price"))
            rank = self._int(obs.get("rank"))
            pct = self._float(obs.get("percent_change"))
            was_seen = rec["observation_count"] > 0
            is_reentry = symbol in entered and was_seen

            if rec["first_seen"] is None:
                rec["first_seen"] = now
            rec["last_seen"] = now
            rec["present"] = True
            rec["observation_count"] += 1
            rec["consecutive_scans"] = 1 if symbol in entered else rec["consecutive_scans"] + 1

            if symbol not in entered:
                prev_price = rec["current_price"]
                prev_rank = rec["current_rank"]
                prev_pct = rec["current_percent_change"]
                rec["price_accel_pct"] = round(((price - prev_price) / prev_price) * 100, 2) if price > 0 and prev_price > 0 else 0.0
                rec["rank_accel"] = (prev_rank - rank) if rank > 0 and prev_rank > 0 else 0
                rec["percent_change_accel"] = round(pct - prev_pct, 2)
            else:
                rec["price_accel_pct"] = rec["rank_accel"] = rec["percent_change_accel"] = 0.0

            rec["previous_price"], rec["current_price"] = rec["current_price"], price
            rec["previous_rank"], rec["current_rank"] = rec["current_rank"], rank
            rec["previous_percent_change"], rec["current_percent_change"] = rec["current_percent_change"], pct

            if symbol in entered:
                previous_entry_price = rec["last_entry_price"]
                previous_entry_rank = rec["last_entry_rank"]
                rec["reentered_recently"] = is_reentry
                if is_reentry:
                    rec["reentry_count"] += 1
                    rec["ignition_timestamp"] = now
                    rec["entry_price_change_pct"] = round(((price - previous_entry_price) / previous_entry_price) * 100, 2) if price > 0 and previous_entry_price > 0 else 0.0
                    rec["rank_improvement"] = previous_entry_rank - rank if rank > 0 and previous_entry_rank > 0 else 0
                else:
                    rec["entry_price_change_pct"] = 0.0
                    rec["rank_improvement"] = 0
                rec["last_entry_price"] = price
                rec["last_entry_rank"] = rank

            self._score_and_classify(rec)

        self.current_universe = current
        return entered, exited

    def observe_technical(self, symbol, *, volume=0, rvol=0, above_vwap=False,
                          vwap_extension=0, hod_distance=999, gain=0, source="TECHNICAL"):
        """Enrich a symbol with scanner metrics, including volume acceleration."""
        self.reset_daily()
        symbol = str(symbol).upper()
        rec = self.symbols.setdefault(symbol, self._new_record(symbol, source))
        volume = self._float(volume)
        previous_volume = rec["current_volume"]
        previous_delta = rec["volume_delta"]
        delta = max(0.0, volume - previous_volume) if previous_volume > 0 else 0.0
        rec["previous_volume"] = previous_volume
        rec["current_volume"] = volume
        rec["previous_volume_delta"] = previous_delta
        rec["volume_delta"] = delta
        rec["volume_accel_ratio"] = round(delta / previous_delta, 2) if delta > 0 and previous_delta > 0 else 0.0
        rec["rvol"] = self._float(rvol)
        rec["above_vwap"] = bool(above_vwap)
        rec["vwap_extension"] = self._float(vwap_extension)
        rec["hod_distance"] = self._float(hod_distance, 999.0)
        rec["gain"] = self._float(gain)
        self._score_and_classify(rec)
        return self.get_context(symbol)

    def _score_and_classify(self, rec):
        score, reasons = 0, []
        persistence = rec["consecutive_scans"]
        if persistence >= 6: score += 20; reasons.append("PERSISTENT")
        elif persistence >= 4: score += 16; reasons.append("PERSISTENT")
        elif persistence >= 3: score += 12; reasons.append("BUILDING")
        elif persistence >= 2: score += 6

        pa = rec["price_accel_pct"]
        if pa >= 5: score += 15; reasons.append("PRICE_SURGE")
        elif pa >= 2: score += 12; reasons.append("PRICE_ACCEL")
        elif pa >= .75: score += 8; reasons.append("PRICE_RISING")
        elif pa > 0: score += 3

        ra = rec["rank_accel"]
        if ra >= 10: score += 15; reasons.append("RANK_SURGE")
        elif ra >= 5: score += 12; reasons.append("RANK_ACCEL")
        elif ra >= 2: score += 8; reasons.append("RANK_RISING")
        elif ra > 0: score += 3

        ga = rec["percent_change_accel"]
        if ga >= 5: score += 10; reasons.append("GAIN_SURGE")
        elif ga >= 2: score += 7; reasons.append("GAIN_ACCEL")
        elif ga >= .75: score += 4

        if rec["reentered_recently"] and rec.get("ignition_timestamp") is not None:
            age = (datetime.now() - rec["ignition_timestamp"]).total_seconds()
            if 0 <= age <= 600:
                score += 10; reasons.append("REENTRY")
            else:
                rec["reentered_recently"] = False

        va = rec["volume_accel_ratio"]
        if va >= 3: score += 15; reasons.append("VOLUME_SURGE")
        elif va >= 2: score += 12; reasons.append("VOLUME_ACCEL")
        elif va >= 1.35: score += 7; reasons.append("VOLUME_RISING")

        if rec["above_vwap"]:
            score += 7; reasons.append("ABOVE_VWAP")
        if rec["hod_distance"] <= 2:
            score += 8; reasons.append("HOD_PRESSURE")
        elif rec["hod_distance"] <= 5:
            score += 4

        score = round(max(0, min(score, 100)), 2)
        old = rec.get("radar_state", "TRACKING")
        extended = rec["vwap_extension"] >= 8 or (rec["gain"] >= 25 and rec["hod_distance"] <= 2)
        cooling = (pa < 0 and ga < 0) or (old in ("IGNITION", "ACTIVE") and score < 30)
        ignition = score >= 60 and (pa >= .75 or ga >= .75 or va >= 1.35 or rec["reentered_recently"])
        active = score >= 50 and rec["above_vwap"] and rec["consecutive_scans"] >= 2
        accelerating = score >= 30 and (pa > 0 or ga > 0 or ra > 0 or va >= 1.35)

        if extended: new = "EXTENDED"
        elif cooling: new = "COOLING"
        elif ignition: new = "IGNITION"
        elif active: new = "ACTIVE"
        elif accelerating: new = "ACCELERATING"
        else: new = "TRACKING"

        rec["radar_score"] = score
        rec["radar_reason"] = "+".join(reasons)
        rec["previous_radar_state"] = old
        rec["radar_state"] = new
        if new != old:
            rec["last_state_change"] = datetime.now()
            self.events.append({
                "timestamp": datetime.now(), "symbol": rec["symbol"], "old_state": old,
                "new_state": new, "score": score, "reason": rec["radar_reason"],
            })

    def get_context(self, symbol):
        rec = self.symbols.get(str(symbol).upper())
        return dict(rec) if rec else {}

    def get_summary(self):
        records = list(self.symbols.values())
        return {
            "tracking": len([r for r in records if r.get("present")]),
            "accelerating": sum(r["radar_state"] == "ACCELERATING" for r in records),
            "ignition": sum(r["radar_state"] == "IGNITION" for r in records),
            "active": sum(r["radar_state"] == "ACTIVE" for r in records),
            "extended": sum(r["radar_state"] == "EXTENDED" for r in records),
            "cooling": sum(r["radar_state"] == "COOLING" for r in records),
        }

    def get_present_records(self):
        return [dict(r) for r in self.symbols.values() if r.get("present")]

    def drain_events(self):
        events = self.events[:]
        self.events.clear()
        return events
