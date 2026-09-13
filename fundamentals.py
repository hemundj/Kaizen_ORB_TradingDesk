import json
import os
import time
import requests

from config import (
    FMP_API_KEY,
    ENABLE_FMP_FUNDAMENTALS,
    FUNDAMENTALS_CACHE_HOURS
)


class FundamentalsEngine:

    def __init__(self):

        self.base_url = "https://financialmodelingprep.com/stable"

        self.cache_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fundamentals_cache.json"
        )

        self.cache = self.load_cache()

    # =====================================
    # CACHE
    # =====================================

    def load_cache(self):

        if not os.path.isfile(self.cache_file):
            return {}

        try:
            with open(
                self.cache_file,
                "r",
                encoding="utf-8"
            ) as f:
                return json.load(f)

        except Exception:
            return {}

    def save_cache(self):

        try:
            with open(
                self.cache_file,
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    self.cache,
                    f,
                    indent=2
                )

        except Exception as e:
            print(
                "FUNDAMENTALS CACHE ERROR:",
                e
            )

    def cache_valid(self, symbol):

        item = self.cache.get(symbol)

        if not item:
            return False

        timestamp = item.get(
            "_cached_at",
            0
        )

        age_seconds = (
            time.time() - timestamp
        )

        max_age = (
            FUNDAMENTALS_CACHE_HOURS
            * 3600
        )

        return age_seconds < max_age

    # =====================================
    # FMP REQUEST
    # =====================================

    def fmp_get(self, endpoint, params):

        if not ENABLE_FMP_FUNDAMENTALS:
            return []

        params = dict(params)

        params["apikey"] = FMP_API_KEY

        url = (
            f"{self.base_url}/"
            f"{endpoint}"
        )

        try:
            response = requests.get(
                url,
                params=params,
                timeout=15
            )

            if response.status_code != 200:

                print(
                    "FMP ERROR:",
                    response.status_code,
                    endpoint,
                    response.text[:300]
                )

                return []

            data = response.json()

            if isinstance(data, list):
                return data

            return []

        except Exception as e:

            print(
                "FMP EXCEPTION:",
                endpoint,
                e
            )

            return []

    # =====================================
    # FUNDAMENTALS
    # =====================================

    def get_symbol_fundamentals(
            self,
            symbol
    ):

        symbol = symbol.upper()

        if self.cache_valid(symbol):
            return self.cache[symbol]

        fundamentals = {
            "Float": 0,
            "SharesOutstanding": 0,
            "FreeFloatPct": 0,
            "MarketCap": 0,
            "Sector": "",
            "Industry": ""
        }

        # -------------------------
        # FLOAT
        # -------------------------

        float_data = self.fmp_get(
            "shares-float",
            {
                "symbol": symbol
            }
        )

        if float_data:

            row = float_data[0]

            fundamentals["Float"] = (
                row.get("floatShares")
                or 0
            )

            fundamentals[
                "SharesOutstanding"
            ] = (
                row.get("outstandingShares")
                or 0
            )

            fundamentals[
                "FreeFloatPct"
            ] = (
                row.get("freeFloat")
                or 0
            )

        # -------------------------
        # PROFILE
        # -------------------------

        profile_data = self.fmp_get(
            "profile",
            {
                "symbol": symbol
            }
        )

        if profile_data:

            row = profile_data[0]

            fundamentals["MarketCap"] = (
                row.get("marketCap")
                or 0
            )

            fundamentals["Sector"] = (
                row.get("sector")
                or ""
            )

            fundamentals["Industry"] = (
                row.get("industry")
                or ""
            )

        fundamentals["_cached_at"] = (
            time.time()
        )

        self.cache[symbol] = fundamentals

        self.save_cache()

        return fundamentals