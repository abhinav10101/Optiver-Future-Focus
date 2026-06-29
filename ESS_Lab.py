"""
Trade Routing Optimization Script
=================================

This script dynamically evaluates system execution handoffs and routes high-priority 
trades to the lowest-latency paths to optimize overall execution performance.

Core Logic:
1. Feature Normalization: Normalizes `trade_count` and `notional_value` to a 0-1 scale.
2. Priority Calculation: Computes a blended priority score weighting notional volume (60%) 
   and market liquidity/trade count (40%).
3. Latency Scoring Metric: Calculates a custom score $S = priority * (12 - rank)$, 
   rewarding handoffs that provide low-latency (better rank) for high-priority flow.
4. Handoff Evaluation: Aggregates total scores across all available handoffs to mathematically 
   identify the top 2 overall performers.
5. Constraint-Based Routing: Isolates the top 15% most critical order flow (>= 85th percentile) 
   and strictly maps them to the identified top 2 handoffs, while leaving standard flow 
   on default routing paths.
"""

import pandas as pd
import numpy as np

def optimize_trade_routing(df):
    # --- 1. Memory Optimization ---
    # Downcast to 8-bit integers to prevent Jupyter kernel crashes
    df['rank'] = df['rank'].astype(np.int8)
    df['handoff_id'] = df['handoff_id'].astype(np.int8)
    
    # --- 2. Vectorized Feature Engineering ---
    df['norm_count'] = df['trade_count'] / df['trade_count'].max()
    df['norm_notional'] = df['notional_value'] / df['notional_value'].max()
    
    # --- 3. Priority & Scoring Logic ---
    # Blending notional volume and market liquidity 
    df['priority'] = (0.6 * df['norm_notional']) + (0.4 * df['norm_count'])
    df['score'] = df['priority'] * (12 - df['rank'])
    
    # --- 4. Handoff Evaluation (The "Why") ---
    # Aggregate comprehensive metrics across ALL handoffs
    handoff_metrics = df.groupby('handoff_id').agg(
        total_score=('score', 'sum'),
        avg_latency_rank=('rank', 'mean'),
        total_trades=('trade_count', 'sum'),
        total_notional=('notional_value', 'sum')
    ).sort_values(by='total_score', ascending=False)
    
    print("--- Handoff Performance Landscape ---")
    print(handoff_metrics.to_string())
    print("\n")
    
    # --- 5. Routing Execution (The "How") ---
    # Dynamically grab the top 2 handoff IDs from our evaluation (e.g., 8 and 4)
    top_handoffs = handoff_metrics.index[:2].tolist()
    print(f"Optimal Handoff Pair: {tuple(top_handoffs)}\n")
    
    # Isolate the top 15% of critical order flow
    high_priority_threshold = df['priority'].quantile(0.85)
    
    # Constraint-based mapping: Route critical flow to the top 2 handoffs
    df['optimized_handoff'] = np.where(
        df['priority'] >= high_priority_threshold,
        np.where(df['handoff_id'] % 2 == 0, top_handoffs[0], top_handoffs[1]), 
        df['handoff_id']  # Retain standard routing for lower priority flow
    )
    
    return df, handoff_metrics

if __name__ == "__main__":
    # Example Execution (Uncomment to run with actual data)
    # df = pd.read_csv('market_data.csv')
    # routed_df, evaluation_summary = optimize_trade_routing(df)
    print("Latency optimization routing script loaded successfully.")
