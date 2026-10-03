"""Market-data provider abstraction for Kaizen.

Scanner/strategy code consumes this interface instead of knowing how a vendor's
HTTP API is shaped. A future Massive/Finnhub/etc. provider can implement the
same methods without changing MarketRadar or the trading logic.
"""
from abc import ABC, abstractmethod
import requests


class MarketDataProvider(ABC):
    name = "UNKNOWN"

    @abstractmethod
    def get_movers(self, top=50):
        """Return normalized mover dicts: symbol, rank, price, change, percent_change."""
        raise NotImplementedError

    @abstractmethod
    def get_snapshots(self, symbols):
        raise NotImplementedError

    @abstractmethod
    def get_bars(self, symbol, timeframe="5Min", limit=200):
        raise NotImplementedError

    @abstractmethod
    def get_daily_bars(self, symbol, limit=20):
        raise NotImplementedError


class AlpacaMarketDataProvider(MarketDataProvider):
    name = "ALPACA"

    def __init__(self, api_key, secret_key, base_url="https://data.alpaca.markets", feed="iex", debug=False):
        self.base_url = base_url.rstrip("/")
        self.feed = feed
        self.debug = debug
        self.headers = {
            "APCA-API-KEY-ID": str(api_key).strip(),
            "APCA-API-SECRET-KEY": str(secret_key).strip(),
        }

    def get_movers(self, top=50):
        url = f"{self.base_url}/v1beta1/screener/stocks/movers"
        try:
            response = requests.get(url, headers=self.headers, params={"top": top}, timeout=15)
            if self.debug:
                print("MOVERS STATUS:", response.status_code)
            if response.status_code != 200:
                if self.debug:
                    print("MOVERS API ERROR:", response.text[:500])
                return []
            gainers = response.json().get("gainers", [])
            if self.debug and gainers:
                print("SAMPLE MOVER DATA:", gainers[0])
                print("RAW GAINERS COUNT:", len(gainers))
            normalized = []
            for rank, item in enumerate(gainers, start=1):
                normalized.append({
                    "symbol": item.get("symbol", ""),
                    "rank": rank,
                    "price": item.get("price", 0),
                    "change": item.get("change", 0),
                    "percent_change": item.get("percent_change", 0),
                    "source": "ALPACA_MOVERS",
                })
            return normalized
        except Exception as exc:
            if self.debug:
                print("MOVERS EXCEPTION:", type(exc).__name__, exc)
            return []

    def get_snapshots(self, symbols):
        if not symbols:
            return {}
        try:
            response = requests.get(
                f"{self.base_url}/v2/stocks/snapshots",
                headers=self.headers,
                params={"symbols": ",".join(symbols)}, timeout=15,
            )
            return response.json() if response.status_code == 200 else {}
        except Exception:
            return {}

    def get_bars(self, symbol, timeframe="5Min", limit=200):
        try:
            response = requests.get(
                f"{self.base_url}/v2/stocks/{symbol}/bars",
                headers=self.headers,
                params={"timeframe": timeframe, "limit": limit, "feed": self.feed},
                timeout=15,
            )
            if response.status_code != 200:
                return []
            clean = []
            for bar in response.json().get("bars") or []:
                if all(key in bar for key in ("o", "h", "l", "c", "v")):
                    clean.append({key: float(bar[key]) for key in ("o", "h", "l", "c", "v")})
            return clean
        except Exception:
            return []

    def get_daily_bars(self, symbol, limit=20):
        try:
            response = requests.get(
                f"{self.base_url}/v2/stocks/{symbol}/bars",
                headers=self.headers,
                params={"timeframe": "1Day", "limit": limit, "feed": self.feed},
                timeout=15,
            )
            return response.json().get("bars", []) if response.status_code == 200 else []
        except Exception:
            return []
