from fundamentals import FundamentalsEngine

engine = FundamentalsEngine()

data = engine.get_symbol_fundamentals(
    "AAPL"
)

print(data)