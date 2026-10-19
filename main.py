import time
import requests
import sqlite3
from datetime import datetime

# Paper trading settings
STARTING_CASH = 100.0
FEE_RATE = 0.006          # 0.6% simulated fee
SLIPPAGE = 0.001          # 0.1% slippage
SYMBOL = "BTC-USD"
CHECK_INTERVAL = 60       # seconds

def get_price():
    url = f"https://api.coinbase.com/v2/prices/{SYMBOL}/spot"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return float(r.json()["data"]["amount"])

def init_db():
    conn = sqlite3.connect("paper_trades.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY, time TEXT, side TEXT, price REAL, size REAL, cash REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS state
                 (key TEXT PRIMARY KEY, value REAL)''')
    c.execute("INSERT OR IGNORE INTO state VALUES ('cash', ?)", (STARTING_CASH,))
    c.execute("INSERT OR IGNORE INTO state VALUES ('btc', 0.0)")
    conn.commit()
    return conn

def get_state(conn):
    c = conn.cursor()
    cash = c.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0]
    btc = c.execute("SELECT value FROM state WHERE key='btc'").fetchone()[0]
    return cash, btc

def update_state(conn, cash, btc):
    c = conn.cursor()
    c.execute("UPDATE state SET value=? WHERE key='cash'", (cash,))
    c.execute("UPDATE state SET value=? WHERE key='btc'", (btc,))
    conn.commit()

def log_trade(conn, side, price, size, cash):
    c = conn.cursor()
    c.execute("INSERT INTO trades (time, side, price, size, cash) VALUES (?, ?, ?, ?, ?)",
              (datetime.utcnow().isoformat(), side, price, size, cash))
    conn.commit()
    print(f"{side.upper()} {size:.6f} BTC @ ${price:.2f} | Cash left: ${cash:.2f}")

def ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema_val = sum(prices[:period]) / period
    for price in prices[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

def main():
    print("Paper trading bot started (BTC-USD EMA 12/26)")
    conn = init_db()
    prices = []

    while True:
        try:
            price = get_price()
            prices.append(price)
            if len(prices) > 50:
                prices = prices[-50:]

            ema12 = ema(prices, 12)
            ema26 = ema(prices, 26)

            cash, btc = get_state(conn)

            if ema12 and ema26:
                # Buy signal
                if ema12 > ema26 and btc == 0 and cash > 10:
                    size = (cash * 0.95) / (price * (1 + SLIPPAGE))
                    cost = size * price * (1 + FEE_RATE + SLIPPAGE)
                    if cost <= cash:
                        cash -= cost
                        btc = size
                        update_state(conn, cash, btc)
                        log_trade(conn, "buy", price, size, cash)

                # Sell signal
                elif ema12 < ema26 and btc > 0:
                    proceeds = btc * price * (1 - FEE_RATE - SLIPPAGE)
                    cash += proceeds
                    log_trade(conn, "sell", price, btc, cash)
                    btc = 0
                    update_state(conn, cash, btc)

            print(f"{datetime.utcnow().strftime('%H:%M:%S')} | Price: ${price:.2f} | Cash: ${cash:.2f} | BTC: {btc:.6f}")

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
