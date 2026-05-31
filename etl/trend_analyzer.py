"""Trend Analysis & Forecasting - Linear regression and Holt-Winters forecasting"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sqlalchemy import create_engine

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


def analyze_all_trends() -> dict[str, Any]:
    """
    Trend analysis for all 100 companies using linear regression.
    Classification: UP / FLAT / DOWN
    """
    try:
        engine = get_database_connection()
        
        query = """
        SELECT 
            company_id,
            company_name,
            year,
            sales
        FROM fact_profit_loss
        WHERE sales IS NOT NULL
        ORDER BY company_id, year
        """
        
        df = pd.read_sql(query, engine)
        
        trends = []
        
        for company_id, group in df.groupby('company_id'):
            company_name = group.iloc[0]['company_name']
            
            if len(group) < 3:  # Need at least 3 years
                continue
            
            # Prepare data for linear regression
            X = np.arange(len(group)).reshape(-1, 1)
            y = group['sales'].values
            
            # Fit linear regression
            model = LinearRegression()
            model.fit(X, y)
            
            # Calculate slope and p-value
            slope = model.coef_[0]
            y_pred = model.predict(X)
            residuals = y - y_pred
            rss = np.sum(residuals ** 2)
            mss = np.sum((y - y.mean()) ** 2)
            r_squared = 1 - (rss / mss) if mss != 0 else 0
            
            # Calculate p-value using scipy
            n = len(X)
            t_stat = slope / (np.sqrt(rss / (n - 2) / np.sum((X - X.mean()) ** 2)) if n > 2 else 1)
            p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - 2)) if n > 2 else 1
            
            # Classify trend
            if p_value < 0.05:  # Statistically significant
                if slope > 0:
                    trend = "UP"
                else:
                    trend = "DOWN"
            else:
                trend = "FLAT"
            
            trends.append({
                "company_id": company_id,
                "company_name": company_name,
                "trend_class": trend,
                "slope": slope,
                "r_squared": r_squared,
                "p_value": p_value,
                "years_analyzed": len(group),
                "detected_at": datetime.utcnow(),
            })
        
        if trends:
            trends_df = pd.DataFrame(trends)
            trends_df.to_sql('fact_trend_analysis', engine, if_exists='append', index=False)
            
            result = {
                "count": len(trends),
                "up_trend": len([t for t in trends if t['trend_class'] == 'UP']),
                "down_trend": len([t for t in trends if t['trend_class'] == 'DOWN']),
                "flat_trend": len([t for t in trends if t['trend_class'] == 'FLAT']),
            }
            logger.info(f"Analyzed trends for {result['count']} companies", extra={"extra_data": result})
            return result
        
        return {"count": 0}
        
    except Exception as e:
        logger.error(f"Error in analyze_all_trends: {str(e)}")
        raise


def forecast_revenue() -> dict[str, Any]:
    """
    Revenue forecasting for top 20 companies using Holt-Winters.
    Generates next-year forecast with confidence intervals.
    """
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        
        engine = get_database_connection()
        
        query = """
        SELECT 
            company_id,
            company_name,
            year,
            sales
        FROM fact_profit_loss
        WHERE sales IS NOT NULL
        ORDER BY company_id, year DESC
        LIMIT 2000
        """
        
        df = pd.read_sql(query, engine)
        
        # Get top 20 companies by latest sales
        top_companies = df.groupby('company_id').agg({
            'sales': 'first',
            'company_name': 'first'
        }).nlargest(20, 'sales').index.tolist()
        
        forecasts = []
        
        for company_id in top_companies:
            company_data = df[df['company_id'] == company_id].sort_values('year')
            
            if len(company_data) < 3:  # Need at least 3 years
                continue
            
            company_name = company_data.iloc[0]['company_name']
            sales_series = company_data['sales'].values
            
            try:
                # Fit Holt-Winters exponential smoothing
                model = ExponentialSmoothing(
                    sales_series,
                    trend='add',
                    seasonal=None,
                    initialization_method='estimated'
                )
                result = model.fit(optimized=True)
                
                # Forecast next year
                forecast = result.forecast(steps=1)[0]
                
                # Calculate confidence interval (simplified)
                std_error = np.std(result.resid) if hasattr(result, 'resid') else np.std(sales_series) * 0.1
                ci_lower = forecast - 1.96 * std_error
                ci_upper = forecast + 1.96 * std_error
                
                forecasts.append({
                    "company_id": company_id,
                    "company_name": company_name,
                    "forecast_year": max(company_data['year']) + 1,
                    "forecast_revenue": forecast,
                    "confidence_lower": ci_lower,
                    "confidence_upper": ci_upper,
                    "model": "holt_winters",
                    "note": "Model estimate, not financial advice",
                    "forecasted_at": datetime.utcnow(),
                })
            except Exception as e:
                logger.warning(f"Forecasting failed for company {company_id}: {str(e)}")
                continue
        
        if forecasts:
            forecasts_df = pd.DataFrame(forecasts)
            forecasts_df.to_sql('fact_revenue_forecast', engine, if_exists='append', index=False)
            
            result = {"count": len(forecasts)}
            logger.info(f"Generated forecasts for {result['count']} companies", extra={"extra_data": result})
            return result
        
        return {"count": 0}
        
    except ImportError:
        logger.warning("statsmodels not installed, skipping Holt-Winters forecasting")
        return {"count": 0, "warning": "statsmodels not installed"}
    except Exception as e:
        logger.error(f"Error in forecast_revenue: {str(e)}")
        raise
