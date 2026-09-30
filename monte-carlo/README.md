_____ . _____                             ______   _____ <br>
|     | |    \   |       /\     |\    |  -        |<br>
|____ | | __ /   |      /  \    | \   | |         |<br>
|     | |   \    |     /____\   |  \  | |         |_____<br>
|     | |    \   |    /      \  |   \ | |         |<br>
|     | |     \  |__ /        \ |    \|  -______  |_____<br>
*github.com/made-in-abyss*
-

"**Itô, K. (1951)**. On stochastic differential equations. Memoirs of the American Mathematical Society, 4, 1–51."
<br><br>
"**Samuelson, P. A. (1965)**. Rational theory of warrant pricing. Industrial Management Review, 6(2), 13–39.
(Or for its application in options: Black, F., & Scholes, M. (1973). The pricing of options and corporate liabilities. Journal of Political Economy, 81(3), 637–654)."<br><br>
"**Parkinson, M. (1980)**. The extreme value method for estimating the variance of the rate of return. The Journal of Business, 53(1), 61–65."
<br><br><br>
-
***"Headrider Simulation:"***<br>
-This is a system built on 2 afforementioned principles. **Headrider** allows you to simulate future asset's price directly off how it is/was.<br><br>
-Unlike your typical newbie's Monte-Carlo, this system is of capability and optimization. Off-loading works to C++ does wonder. <br><br>
-Firstly, the system fetches asset's historical datas via *ccxt*, then *Drift, Volatility* are meticulously calculated via **Parkinson Variance**.<br><br>
-After off-loading to the C++ engine, the system begins simulating **Geometric Brownian** path trajectory, incorporating regime-switching mechanism (to prevent "forever trend") and **Itô's lemma** for standard deviation correction.<br><br>


