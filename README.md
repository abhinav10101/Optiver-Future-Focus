# Optiver-Future-Focus

# High-Frequency Volatility Forecasting Engine

## The Assignment
The objective of this project was to build a robust quantitative model to predict the short-term volatility (target variance) of five distinct assets (Stocks 0-4). We were provided with high-frequency market data segmented into non-sequential, 10-minute trading buckets (`time_id`), containing second-by-second tick data and log returns. 

The primary challenge was to outperform a naive baseline model (which calculated simple unweighted historical variance) by identifying and exploiting structural market micro-patterns without overfitting to the heavy noise inherent in high-frequency financial data.

## Our Approach & Architecture
To solve this, we designed a two-stage, co-dependent prediction engine that models both temporal decay and cross-asset correlation.

### Stage 1: Exponential Recency Weighting
Financial volatility is highly autoregressive; events that happen closer to the end of a trading bucket have a higher predictive power for the immediate future. Instead of treating every second equally, we engineered a base model that calculates variance using an exponential decay function.
* **The Math:** Each second $t$ in the bucket (from 0 to 599) was assigned a weight using the function $w_t = C + e^{x \cdot t}$. 
* **Optimization:** We optimized the hyperparameters $(C, x)$ uniquely for each stock using a grid search, effectively teaching the model exactly how heavily to prioritize late-bucket price action over early-bucket action.

### Stage 2: Cross-Sectional Peer Blending
Assets do not trade in a vacuum; volatility in one stock is often a delayed reaction to a broader market shock seen in another. To capture this, we built a cross-asset blending matrix.
* **The Strategy:** A stock's final variance prediction is not just based on its own history, but is a weighted sum of the base predictions of all five stocks in the market.
* **Optimization:** We executed a highly vectorized coordinate descent framework, testing tens of thousands of weight combinations simultaneously to find the exact percentage of peer influence that minimized error. For example, Stock 2's optimal prediction heavily relies on its own data (85%) but also draws a strong signal from Stock 1 (15%).

## Validation & Anomaly Detection
A critical part of our workflow was ensuring the model generalized to unseen market regimes rather than memorizing historical noise. 

* **Micro-Seasonality Testing:** We investigated whether specific seconds inside the 10-minute buckets exhibited consistent, structural spikes in volatility (e.g., algorithmic trading sweeps at the 5-minute mark). 
* **Outlier Rejection:** While raw averages showed massive variance spikes at specific timestamps (e.g., second 46 and 262), our validation scripts proved these were isolated outlier events—in one case, a single historic trade accounted for 72.2% of the variance at that timestamp. By verifying this, we successfully avoided hardcoding biased weights and prevented the model from catastrophic overfitting.

## The Results
The dual-layer architecture performed exceptionally well, achieving a massive reduction in error on unseen, out-of-sample market data.

* **Baseline Model RMSE:** $6.11 \times 10^{-5}$
* **Optimized Model Validation RMSE:** $2.13 \times 10^{-5}$
* **Impact:** We successfully reduced the predictive error by **over 63%**, proving that the combination of exponential time-weighting and cross-asset correlation successfully isolates true market alpha from random noise.

# Trade Routing Optimization

## The Assignment
The primary objective of this project was to analyze trade execution metrics and minimize system latency for critical order flows. The challenge was to mathematically evaluate and identify the most efficient system "handoffs" based on empirical performance data (specifically evaluating trade frequency, order count, and notional volume) rather than relying on arbitrary or default routing paths.

## Our Approach
We developed a quantitative scoring model paired with a constraint-based routing algorithm to dynamically allocate high-value trades to the fastest available paths. 

* **Feature Normalization:** We normalized `trade_count` and `notional_value` to a 0-1 scale to ensure uniform evaluation across disparate metrics.
* **Priority Calculation:** We computed a blended priority score that weighted notional volume at 60% and market liquidity/trade count at 40%.
* **Latency Scoring Metric:** We formulated a custom evaluation metric, S = priority * (12 - rank), rewarding handoffs that consistently provided better latency ranks for high-priority flow.
* **Handoff Evaluation:** By aggregating total scores across the dataset, we were able to mathematically identify the top two overall performing handoffs (Handoffs 4 and 8).
* **Constraint-Based Routing:** We isolated the top 15% most critical order flow (>= 85th percentile) and engineered a strict mapping function to route these trades exclusively to the identified top two handoffs, leaving standard flow on default routing paths.

# Optibook FF2026: Algorithmic Trading Competition

## Assignment Description

The objective of this assignment was to design, develop, and deploy an autonomous trading strategy from scratch to compete in a live exchange simulation against 23 other teams. The exchange featured multiple asset classes, including liquid equities (stocks), derivatives (futures), and an ETF. Rather than prescribing a specific algorithm, the assignment was completely open-ended, requiring teams to identify structural market inefficiencies, engineer risk management protocols, and maximize portfolio returns under live execution constraints. 

Through robust execution and risk handling, our implemented framework successfully navigated the cross-asset environment, securing **4th place out of 24 competing teams**.

## Strategy Implementation: Penny-The-Market (`Optibook.py`)

To capture consistent alpha across the multi-asset exchange, we engineered an aggressive, high-frequency "Penny-The-Market" market-making strategy. The approach was designed to dynamically squeeze the spread and extract edge while heavily mitigating inventory risk.

### 1. Causal Volatility & State Tracking
To ensure the trading framework operated without look-ahead bias, the bot continuously monitored order book dynamics using a strictly historical, 60-tick rolling window. The mid-prices were utilized to dynamically calculate the rolling standard deviation ($\sigma$), serving as a pure causal input for defining real-time volatility across the designated instruments (`AMZN`, `JPM`, `XOM`).

### 2. Inventory-Skewed Valuation Model
To manage the multi-asset risk, we implemented an asymmetric pricing model that actively skewed quotes based on accumulated inventory ($q$) and asset volatility:
* **Reservation Price ($r$):** The theoretical fair value shifted away from the mid-price as positions grew to discourage adverse selection, incorporating a one-tick floor to remain highly responsive even during low-volatility regimes:
    $$r = \text{mid} - q \cdot \gamma \cdot (\sigma^2 + \text{TICK})$$
* **Dynamic Half-Spread ($h$):** The spread widened or narrowed dynamically to balance competitive execution with a strict risk premium based on market volatility and position distress:
    $$h = \max(h_{min}, h_{base} + k_{vol} \cdot \sigma + \gamma \cdot |q| \cdot \text{TICK})$$
* **Theoretical Boundaries:** This established our ideal target bounds, defining the absolute worst prices we would accept for a bid ($P_{bid}^*$) or ask ($P_{ask}^*$):
    $$P_{bid}^* = r - h$$
    $$P_{ask}^* = r + h$$

### 3. The Pennying & Priority Execution Engine
To outcompete other teams on execution speed and queue priority, the strategy actively monitored the public best bid ($B_{public}$) and best ask ($A_{public}$). 
* If our order was not currently topping the book, the script aggressively undercut or joined the best public quote by a single tick ($B_{public} + \text{TICK}$) to capture order flow.
* To prevent toxic execution, this target was strictly clamped against our theoretical ideal boundaries and protected against crossed or locked markets:
    $$\text{Final Target Bid} = \min(P_{bid}^*, B_{target}, A_{public} - \text{TICK})$$

### 4. Risk Infrastructure & Operational Safeguards
* **Inventory Gating:** Hard caps (`POS_LIMIT = 100`) and soft boundaries (`SOFT_LIMIT = 70`) were structurally integrated. If the portfolio breached the soft threshold on a specific asset, the bot instantly halted the accumulation side, only quoting orders that reduced net exposure.
* **Rate-Limit Shield:** A deque-based `RateLimiter` tracked transaction timestamps to ensure our high-frequency requoting never violated the exchange message budget (`MSG_BUDGET = 15`), completely avoiding order rejection penalties.
* **Latency Mitigation:** The bot used a `needs_requote` mechanism, ignoring noisy micro-fluctuations and only modifying orders if the price shifted by a meaningful threshold (`REQUOTE_TICKS`), saving critical bandwidth.
* **Connection Resilience:** A dedicated asynchronous safety loop handled socket drops via exponential backoff, clearing out stale orders immediately upon reconnection to wipe out residual execution risk.
