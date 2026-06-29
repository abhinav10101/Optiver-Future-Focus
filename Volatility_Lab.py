import csv
import numpy as np
import pandas as pd

# =====================================================================
# 1. CORE CORE LOGIC & MATHEMATICAL FUNCTIONS
# =====================================================================

def _var_unweighted(group):
    """
    Naive baseline model: Calculates unweighted historical variance 
    of log returns for a given stock/time group.
    """
    if len(group) < 2:
        return 0.0
    return np.var(group['log_return'], ddof=1)


def _var_weighted_exp(group, C, x):
    """
    Calculates the recency-weighted variance using an exponential decay function.
    Weights are assigned based on the 'seconds_in_bucket' column.
    """
    if len(group) < 2:
        return 0.0
    
    # Calculate weights based on the second of execution (0 to 599)
    # Formula: C + exp(x * t)
    t = group['seconds_in_bucket'].values
    weights = C + np.exp(x * t)
    
    # Extract log returns
    returns = group['log_return'].values
    
    # Calculate weighted mean
    sum_w = np.sum(weights)
    if sum_w <= 0:
        return 0.0
    weighted_mean = np.sum(returns * weights) / sum_w
    
    # Calculate weighted variance (biased/unbiased scaling)
    squared_diff = (returns - weighted_mean) ** 2
    weighted_var = np.sum(weights * squared_diff) / sum_w
    
    return float(weighted_var)


def predict_weighted_exp(df, prediction_index, params_dict):
    """
    Generates base exponential predictions for all target pairs in the index.
    """
    # Create a structured container for predictions
    preds = pd.Series(index=prediction_index, dtype=float).fillna(0.0)
    
    # Group dataframe to efficiently loop through chunks
    grouped = df.groupby(['stock_id', 'time_id'], sort=True)
    
    for (stock_id, time_id), group in grouped:
        if (stock_id, time_id) in preds.index:
            # Retrieve specific hyper-parameters for this stock
            C, x = params_dict.get(stock_id, (0, 0.01))
            preds.loc[(stock_id, time_id)] = _var_weighted_exp(group, C, x)
            
    return preds


# =====================================================================
# 2. MAIN SUBMISSION GENERATION ENGINE
# =====================================================================

def predict_YOUR_MODEL_HERE(df, prediction_index):
    """
    The final submission model combining Stage 1 (Exponential Weighting)
    and Stage 2 (Cross-Stock Peer Blending).
    """
    # Hardcoded optimal Stage 1 exponential decay parameters (C, x) from training
    best_weighted_params = {
        0: (0, 0.05),
        1: (0, 0.001),
        2: (0, 0.01),
        3: (0, 0.005),
        4: (0, 0.02)
    }
    
    # Hardcoded optimal Stage 2 peer influence weights from training
    best_blend_weights = {
        0: {0: 0.30, 1: 0.30, 2: 0.35, 3: 0.00, 4: 0.05},
        1: {0: 0.00, 1: 1.00, 2: 0.00, 3: 0.00, 4: 0.00},
        2: {0: 0.00, 1: 0.15, 2: 0.85, 3: 0.00, 4: 0.00},
        3: {0: 0.15, 1: 0.00, 2: 0.35, 3: 0.50, 4: 0.00},
        4: {0: 0.05, 1: 0.00, 2: 0.60, 3: 0.00, 4: 0.35}
    }
    
    # Find all available pairs in the current evaluation chunk to ensure peers can be accessed
    all_pairs_index = df.groupby(["stock_id", "time_id"], sort=True).groups.keys()
    all_pairs_multi_index = pd.MultiIndex.from_tuples(all_pairs_index, names=["stock_id", "time_id"])
    
    # Generate base exponential predictions for all pairs
    base_preds = predict_weighted_exp(df, all_pairs_multi_index, best_weighted_params)
    base_preds_df = base_preds.unstack(level='stock_id')
    
    blended_series_list = []
    
    # Apply cross-sectional blending matrix math
    for target_stock, weights_dict in best_blend_weights.items():
        if target_stock not in base_preds_df.columns:
            continue
            
        # Build weight array aligned specifically to the existing columns in this chunk
        w_array = np.array([weights_dict.get(col, 0.0) for col in base_preds_df.columns])
        
        # Guard against missing peer data by normalizing available columns
        if w_array.sum() > 0:
            w_array = w_array / w_array.sum()
        else:
            w_array = np.zeros(len(base_preds_df.columns))
            if target_stock in base_preds_df.columns:
                w_array[base_preds_df.columns.get_loc(target_stock)] = 1.0
                
        # Perform cross-sectional blend matrix product
        blended = (base_preds_df * w_array).sum(axis=1)
        blended.index = pd.MultiIndex.from_product([[target_stock], blended.index], names=['stock_id', 'time_id'])
        blended_series_list.append(blended)
        
    # Combine and realign predictions precisely to match the grader's index format
    final_predictions = pd.concat(blended_series_list).reindex(prediction_index).fillna(0.0)
    return final_predictions


# =====================================================================
# 3. RUNTIME PIPELINE EXECUTION
# =====================================================================

if __name__ == "__main__":
    print("🚀 Loading data structures...")
    # These variables are assumed to be loaded in your workspace environment:
    # df          -> Raw dataset containing market logs
    # target_vars -> Series containing ground truth training labels
    
    # Extract structural layout
    all_pairs = pd.MultiIndex.from_frame(
        df[["stock_id", "time_id"]].drop_duplicates().sort_values(["stock_id", "time_id"]),
    )
    
    # Uncover the hidden test pairs the platform wants you to predict
    missing_prediction_index = all_pairs.difference(target_vars.index)
    print(f"📋 Found {len(missing_prediction_index)} test pairs to predict.")
    
    print("🧠 Evaluating multi-stage inference engine...")
    predicted_vars_TO_SUBMIT = predict_YOUR_MODEL_HERE(df, missing_prediction_index)
    
    print("💾 Writing predictions directly to my_submission.csv...")
    with open('my_submission.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['stock_id', 'time_id', 'prediction'])
        for (stock_id, time_id), value in predicted_vars_TO_SUBMIT.items():
            writer.writerow([stock_id, time_id, value])
            
    print("✨ Execution complete. 'my_submission.csv' is optimized and ready!")