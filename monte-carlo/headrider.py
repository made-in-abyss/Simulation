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
n = int(input("how many time: "))
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
input_data = f"{n} {daily_drift} {daily_vol} {starting_price}"

result = subprocess.run(
    [binary_path],
    input=input_data,
    text=True,
    capture_output=True,
    check=True,
)
lines = result.stdout.strip().split("\n")
p10 = numpy.fromstring(lines[0], sep=" ")
p50 = numpy.fromstring(lines[1], sep=" ")
p90 = numpy.fromstring(lines[2], sep=" ")
datas = numpy.fromstring(lines[3], sep=" ")

print(f"90% Worstcase: {datas[0]}\n90% Drawdown: {datas[1]*100}%")
sim_x = range(HISTORICAL_TIME, HISTORICAL_TIME + 1000)
plt.plot(range(HISTORICAL_TIME), close, label="Historical Data", color="black")
plt.plot(sim_x, p50, label="Median Trajectory (50%)", color="#1f77b4")
plt.fill_between(
    sim_x,
    p10,
    p90,
    color="#1f77b4",
    alpha=0.25,
    label="Confidence Band (10%-90%)",
)
plt.axvline(x=HISTORICAL_TIME, color="gray", linestyle="--")
plt.legend(loc="upper left")
plt.show()
