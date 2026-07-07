from scanner import KaizenScanner
from market import market_is_open

print("\n")
print("=" * 60)
print("KAIZEN ORB TRADING DESK")
print("=" * 60)

if market_is_open():

    print("Market Status : OPEN")

else:

    print("Market Status : CLOSED")

print("Scan Mode     : COMBINED")
print("=" * 60)

scanner = KaizenScanner()

df = scanner.run_scan(
    mode="watchlist"

)

if df.empty:

    print(
        "\nNo qualifying setups found."
    )

else:

    print("\n")

    print(
        df.to_string(
            index=False
        )
    )