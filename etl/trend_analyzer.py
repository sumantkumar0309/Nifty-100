"""
Trend Analysis and Forecasting Module

Detects trends and forecasts revenue using:
1. Linear regression: Classify trend as UP/FLAT/DOWN based on 5-year data
2. ARIMA/Holt-Winters: Forecast next year's revenue for top 20 companies
3. Trend labels and forecasted values stored to PostgreSQL
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text

from backend2.logging_utils import get_logger

logger = get_logger(__name__)


def get_database_connection():
    """Get PostgreSQL database connection using SQLAlchemy."""
    from sqlalchemy import create_engine
    import os
    
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/nifty100_warehouse"
    )
    return create_engine(db_url)


def analyze_trends() -> dict[str, Any]:
    """
    Classify trend as UP/FLAT/DOWN for all companies using linear regression on 5-year sales data.
    Returns counts of companies in each trend category.
    """
    try:
        engine = get_database_connection()
        
        # Load 5-year sales data for all companies
        query = """
        SELECT 
            company_id, year, sales
        FROM fact_profit_loss
        WHERE sales IS NOT NULL
        ORDER BY company_id, year DESC
        LIMIT 500  -- Last 5 years across 100 companies
        """
        
        df = pd.read_sql(query, engine)
        
        trends = []
        
        for company_id in df['company_id'].unique():
            company_data = df[df['company_id'] == company_id].sort_values('year')
            
            if len(company_data) < 3:
                continue  # Need at least 3 data points
            
            # Linear regression on sales
            X = np.arange(len(company_data)).reshape(-1, 1)
            y = company_data['sales'].values
            
            slope, intercept, r_value, p_value, std_err = stats.linregress(X.flatten(), y)
            
            # Classify trend
            if p_value < 0.05 and slope > 0:  # Statistically significant positive trend
                trend_label = "UP"
            elif p_value < 0.05 and slope < 0:  # Statistically significant negative trend
                trend_label = "DOWN"
            else:
                trend_label = "FLAT"
            
            # Also check profit trend
            profit_data = company_data[['year']].copy()
            if 'net_profit' in company_data.columns:
                profit_data['net_profit'] = company_data['net_profit'].values
                if len(profit_data['net_profit'].dropna()) > 0:
                    y_profit = profit_data['net_profit'].dropna().values
                    if len(y_profit) >= 3:
                        slope_profit, _, _, _, _ = stats.linregress(
                            np.arange(len(y_profit)), y_profit
                        )
                    else:
                        slope_profit = slope
                else:
                    slope_profit = slope
            else:
                slope_profit = slope
            
            trends.append({
                'company_id': company_id,
                'trend_label': trend_label,
                'sales_slope': slope,
                'profit_slope': slope_profit,
                'r_squared': r_value ** 2,
                'years_analyzed': len(company_data),
                'detected_at': datetime.utcnow()
            })
        
        if trends:
            trends_df = pd.DataFrame(trends)
            trends_df.to_sql('fact_trend_analysis', engine, if_exists='append', index=False)
            
            result = {
                "count": len(trends_df),
                "up_count": len(trends_df[trends_df['trend_label'] == 'UP']),
                "flat_count": len(trends_df[trends_df['trend_label'] == 'FLAT']),
                "down_count": len(trends_df[trends_df['trend_label'] == 'DOWN']),
            }
            logger.info(f"Analyzed trends for {result['count']} companies", extra={"extra_data": result})
            return result
        
        return {"count": 0, "up_count": 0, "flat_count": 0, "down_count": 0}
        
    except Exception as e:
        logger.error(f"Error in analyze_trends: {str(e)}")
        raise


def forecast_top_companies() -> dict[str, Any]:
    """
    Forecast next year's revenue for top 20 companies by revenue using Holt-Winters method.
    Returns forecast summary with confidence intervals.
    """
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        
        engine = get_database_connection()
        
        # Get top 20 companies by latest revenue
        query = """
        SELECT 
            c.company_id,
            c.company_name,
            MAX(pl.sales) as latest_sales
        FROM dim_company c
        JOIN fact_profit_loss pl ON c.company_id = pl.company_id
        GROUP BY c.company_id, c.company_name
        ORDER BY latest_sales DESC
        LIMIT 20
        """
        
        top_companies = pd.read_sql(query, engine)
        
        forecasts = []
        
        for idx, row in top_companies.iterrows():
            company_id = row['company_id']
            company_name = row['company_name']
            
            # Get historical sales data for this company (last 5 years)
            hist_query = f"""
            SELECT year, sales FROM fact_profit_loss
            WHERE company_id = {company_id}
            ORDER BY year
            LIMIT 5
            """
            
            hist_df = pd.read_sql(hist_query, engine)
            
            if len(hist_df) < 3:
                continue  # Need at least 3 data points
            
            try:
                # Fit Holt-Winters exponential smoothing
                sales_values = hist_df['sales'].values
                
                # Ensure positive values
                if (sales_values <= 0).any():
                    sales_values = np.abs(sales_values) + 1
                
                model = ExponentialSmoothing(
                    sales_values,
                    trend='add' if len(sales_values) >= 3 else None,
                    seasonal=None,
                    initialization_method='estimated'
                )
                fitted_model = model.fit(optimized=True)
                
                # Forecast next year
                forecast_value = fitted_model.forecast(steps=1)[0]
                
                # Calculate confidence interval (simplified: ±10% of forecast)
                confidence_interval = forecast_value * 0.1
                
                forecasts.append({
                    'company_id': company_id,
                    'company_name': company_name,
                    'forecast_revenue': max(0, forecast_value),  # Ensure non-negative
                    'confidence_lower': max(0, forecast_value - confidence_interval),
                    'confidence_upper': forecast_value + confidence_interval,
                    'method': 'holt_winters',
                    'forecast_for_year': datetime.utcnow().year + 1,
                    'forecast_date': datetime.utcnow(),
                    'disclaimer': 'Model estimate, not financial advice'
                })
                
            except Exception as e:
                logger.warning(f"Forecast failed for company {company_id}: {str(e)}")
                continue
        
        if forecasts:
            forecasts_df = pd.DataFrame(forecasts)
            forecasts_df.to_sql('fact_revenue_forecast', engine, if_exists='append', index=False)
            
            result = {"count": len(forecasts_df)}
            logger.info(f"Generated forecasts for {result['count']} top companies", extra={"extra_data": result})
            return result
        
        return {"count": 0}
        
    except ImportError:
        logger.warning("statsmodels not installed. Skipping Holt-Winters forecasting.")
        return {"count": 0, "note": "statsmodels required for forecasting"}
    except Exception as e:
        logger.error(f"Error in forecast_top_companies: {str(e)}")
        raise
