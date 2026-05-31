"""Anomaly Detection Module - Z-score and Isolation Forest anomaly detection"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy import create_engine, text

from backend2.logging_utils import get_logger

logger = get_logger(__name__)


def get_database_connection():
    """Get PostgreSQL database connection using SQLAlchemy"""
    import os
    
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/nifty100_warehouse"
    )
    return create_engine(db_url)


def detect_anomalies_zscore() -> dict[str, Any]:
    """
    Z-score anomaly detection: Identify data points > 3 std deviations from mean.
    Analyzes: sales, net_profit, borrowings, operating_profit.
    """
    try:
        engine = get_database_connection()
        
        # Load fact_profit_loss data
        query = """
        SELECT 
            company_id, year,
            sales, net_profit,
            operating_profit, interest
        FROM fact_profit_loss
        WHERE sales IS NOT NULL OR net_profit IS NOT NULL
        ORDER BY company_id, year
        """
        
        df_pl = pd.read_sql(query, engine)
        
        # Load fact_balance_sheet data
        query_bs = """
        SELECT 
            company_id, year,
            borrowings, equity_capital
        FROM fact_balance_sheet
        WHERE borrowings IS NOT NULL
        ORDER BY company_id, year
        """
        
        df_bs = pd.read_sql(query_bs, engine)
        
        anomalies = []
        
        # Z-score analysis for profit_loss metrics
        for metric in ['sales', 'net_profit', 'operating_profit']:
            if metric in df_pl.columns:
                df_pl[f'{metric}_zscore'] = np.abs(_zscore_normalized(df_pl[metric]))
                anomaly_mask = df_pl[f'{metric}_zscore'] > 3
                anomalies_subset = df_pl[anomaly_mask][['company_id', 'year', metric, f'{metric}_zscore']]
                anomalies_subset['metric'] = metric
                anomalies.append(anomalies_subset)
        
        # Z-score analysis for balance sheet metrics
        for metric in ['borrowings']:
            if metric in df_bs.columns:
                df_bs[f'{metric}_zscore'] = np.abs(_zscore_normalized(df_bs[metric]))
                anomaly_mask = df_bs[f'{metric}_zscore'] > 3
                anomalies_subset = df_bs[anomaly_mask][['company_id', 'year', metric, f'{metric}_zscore']]
                anomalies_subset['metric'] = metric
                anomalies.append(anomalies_subset)
        
        if anomalies:
            anomalies_df = pd.concat(anomalies, ignore_index=True)
            anomalies_df['anomaly_type'] = 'zscore'
            anomalies_df['detected_at'] = datetime.utcnow()
            anomalies_df['severity'] = anomalies_df.apply(
                lambda row: 'critical' if row.get(f"{row['metric']}_zscore", 0) > 5 else 'warning',
                axis=1
            )
            
            # Store anomalies in database
            anomalies_df.to_sql('fact_anomaly_flags', engine, if_exists='append', index=False)
            
            result = {"count": len(anomalies_df)}
            logger.info(f"Z-score detected {result['count']} anomalies", extra={"extra_data": result})
            return result
        
        return {"count": 0}
        
    except Exception as e:
        logger.error(f"Error in detect_anomalies_zscore: {str(e)}")
        raise


def detect_anomalies_isolation_forest() -> dict[str, Any]:
    """
    Isolation Forest anomaly detection: ML-based unsupervised learning.
    Creates feature matrix and flags statistical outliers.
    """
    try:
        engine = get_database_connection()
        
        # Load comprehensive feature matrix
        query = """
        SELECT 
            c.company_id,
            c.company_name,
            pl.year,
            pl.sales,
            pl.net_profit,
            pl.operating_profit,
            pl.opm_pct,
            bs.borrowings,
            bs.debt_to_equity,
            cf.operating_activity,
            cf.free_cash_flow
        FROM dim_company c
        LEFT JOIN fact_profit_loss pl ON c.company_id = pl.company_id
        LEFT JOIN fact_balance_sheet bs ON c.company_id = bs.company_id AND bs.year = pl.year
        LEFT JOIN fact_cash_flow cf ON c.company_id = cf.company_id AND cf.year = pl.year
        WHERE pl.year IS NOT NULL
        ORDER BY c.company_id, pl.year
        """
        
        df = pd.read_sql(query, engine)
        
        # Select numeric features and drop NaN
        feature_cols = [
            'sales', 'net_profit', 'operating_profit', 'opm_pct',
            'borrowings', 'debt_to_equity', 'operating_activity', 'free_cash_flow'
        ]
        
        X = df[feature_cols].fillna(df[feature_cols].median())
        
        # Normalize features (0-1 scale)
        X_normalized = (X - X.min()) / (X.max() - X.min() + 1e-8)
        
        # Apply Isolation Forest
        iso_forest = IsolationForest(
            contamination=0.05,  # Assume 5% of data are anomalies
            random_state=42,
            n_estimators=100
        )
        
        df['anomaly_score'] = iso_forest.fit_predict(X_normalized)
        anomalies_df = df[df['anomaly_score'] == -1].copy()
        
        if len(anomalies_df) > 0:
            anomalies_df['anomaly_type'] = 'isolation_forest'
            anomalies_df['detected_at'] = datetime.utcnow()
            anomalies_df['severity'] = 'warning'
            
            # Store anomalies in database
            anomalies_df[['company_id', 'company_name', 'year', 'anomaly_type', 'detected_at', 'severity']].to_sql(
                'fact_anomaly_flags', engine, if_exists='append', index=False
            )
            
            result = {"count": len(anomalies_df)}
            logger.info(f"Isolation Forest detected {result['count']} anomalies", extra={"extra_data": result})
            return result
        
        return {"count": 0}
        
    except Exception as e:
        logger.error(f"Error in detect_anomalies_isolation_forest: {str(e)}")
        raise


def _zscore_normalized(series: pd.Series) -> pd.Series:
    """Normalize series to z-scores"""
    mean = series.mean()
    std = series.std()
    if std == 0:
        return (series - mean).fillna(0)
    return (series - mean) / std
