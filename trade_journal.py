import pandas as pd


class TradeJournal:

    def __init__(self):

        self.file = "trade_log.csv"

    def load_trades(self):

        try:

            df = pd.read_csv(self.file)

            # Remove completely empty rows
            df = df.dropna(
                how="all"
            )

            # Remove rows without ticker
            df = df.dropna(
                subset=["Ticker"]
            )

            # Clean ticker formatting
            df["Ticker"] = (
                df["Ticker"]
                .astype(str)
                .str.upper()
                .str.strip()
            )

            # Convert dates
            df["Trade Date"] = pd.to_datetime(
                df["Trade Date"],
                errors="coerce"
            )

            # Remove rows with no valid date
            df = df.dropna(
                subset=["Trade Date"]
            )

            df["Day Available to Trade"] = pd.to_datetime(
                df["Day Available to Trade"],
                errors="coerce"
            )

            return df

        except Exception as e:

            print(
                "Trade Journal Error:",
                e
            )

            return pd.DataFrame()

    def get_wash_sale_symbols(self):

        trades = self.load_trades()

        if trades.empty:
            return {}

        today = pd.Timestamp.today()

        wash_symbols = {}

        for _, row in trades.iterrows():

            symbol = row["Ticker"]

            available_date = row["Day Available to Trade"]

            if pd.isna(available_date):
                continue

            days_remaining = (
                    available_date - today
            ).days

            if days_remaining >= 0:
                wash_symbols[symbol] = {
                    "days_remaining": days_remaining,
                    "available_date": available_date.strftime("%Y-%m-%d")
                }

        return wash_symbols



if __name__ == "__main__":

    journal = TradeJournal()

    trades = journal.load_trades()

    print("\nCLEAN TRADES")
    print(trades.head())


    print("\nWASH SALE WATCHLIST")

    blocked = journal.get_wash_sale_symbols()

    print(blocked)