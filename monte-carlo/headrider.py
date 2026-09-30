import os
import subprocess
import yfinance
import numpy
import ccxt
import matplotlib.pyplot as plt
##   _____ . _____    |                        ______  ._____
##   |     | |    \   |       /\     |\    |  /        |
##   |____ | | __ /   |      /  \    | \   | |         |
##   |     | |   \    |     /____\   |  \  | |         |_____
##   |     | |    \   |    /      \  |   \ | |         |
##   |     | |     \  |__ /        \ |    \|  \______  |_____
##   github.com/made-in-abyss

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
exe_name = "monte_carlo_engine.exe" if os.name == "nt" else "monte_carlo_engine"
binary_path = os.path.join(SCRIPT_DIR, exe_name)
cpp_path = os.path.join(SCRIPT_DIR, "main.cpp")
if not os.path.exists(binary_path):
  print("Compiling")
  subprocess.run(["g++", "-O3", cpp_path, "-o", binary_path], check=True)

lx = []
ly = []
exchange = ccxt.binance({
    'enableRateLimit': True
})


HISTORICAL_TIME = 100
tick_name = str(input("pls input your ticker: "))
ohlcv = exchange.fetch_ohlcv(tick_name, timeframe='1d', limit=HISTORICAL_TIME)

open = numpy.array([candles[1] for candles in ohlcv])
high = numpy.array([candles[2] for candles in ohlcv])
low =numpy.array([candles[3] for candles in ohlcv])
close = numpy.array([candles[4] for candles in ohlcv])

log_hl_ratio = numpy.log(high/low)
log_return = numpy.log(close[1:]/close[:-1])
parkinson_variance = (1.0 / (4.0*numpy.log(2))) * (log_hl_ratio**2)

daily_drift = numpy.mean(log_return) * 0.2
starting_price = close[len(close)-1]
daily_vol = numpy.sqrt(numpy.mean(parkinson_variance))
input_data = f"{daily_drift} {daily_vol} {starting_price}"

result = subprocess.run(
    [binary_path],
    input=input_data,
    text=True,
    capture_output=True,
    check=True,
)
simulated_prices = numpy.fromstring(result.stdout.strip(), sep=" ")

for i in range(0,HISTORICAL_TIME):
    lx.append(i)
    ly.append(close[i])

for i in range(0,1000):
    lx.append(i+HISTORICAL_TIME)
    ly.append(simulated_prices[i])

plt.plot(lx,ly,label="Price")
plt.title(f"Simulated price of {tick_name}")
plt.xlabel("Time (days)")
plt.ylabel("Price")
plt.legend(loc='lower right')
plt.show()
