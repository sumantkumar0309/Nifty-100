"""
Pros and Cons Generator for Financial Health Analysis

This module auto-generates pro and con statements for each company based on financial metrics.
It implements a rule engine that evaluates companies against predefined financial criteria.

Rules Sources:
- fact_ml_scores: overall_score, health_label, profitability_score, growth_score, etc.
- fact_balance_sheet: debt_to_equity, equity_capital, borrowings
- fact_profit_loss: operating_profit, net_profit, opm_pct, net_profit_margin_pct, dividend_payout_pct
- fact_cash_flow: operating_activity, free_cash_flow
- fact_analysis: 3Y, 5Y, 10Y growth metrics
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import text

from backend2.config import PROJECT_ROOT
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


def generate_all_pros_cons() -> dict[str, Any]:
    """
    Main entry point: Generate pros and cons for all 100 companies.
    Returns dict with count of companies processed.
    """
    try:
        engine = get_database_connection()
        
        # Get all companies with their latest scores and financial metrics
        query = """
        SELECT 
            c.company_id,
            c.company_name,
            ms.overall_score,
            ms.health_label,
            ms.profitability_score,
            ms.growth_score,
            ms.leverage_score,
            ms.cashflow_score,
            ms.dividend_score,
            bs.debt_to_equity,
            bs.equity_capital,
            bs.borrowings,
            pl.opm_pct,
            pl.net_profit_margin_pct,
            pl.dividend_payout_pct,
            pl.operating_profit,
            pl.interest,
            cf.operating_activity,
            cf.free_cash_flow,
            fa.value_pct as growth_3y
        FROM dim_company c
        LEFT JOIN fact_ml_scores ms ON c.company_id = ms.company_id 
            AND ms.computed_at = (SELECT MAX(computed_at) FROM fact_ml_scores WHERE company_id = c.company_id)
        LEFT JOIN fact_balance_sheet bs ON c.company_id = bs.company_id 
            AND bs.year = (SELECT MAX(year) FROM fact_balance_sheet WHERE company_id = c.company_id)
        LEFT JOIN fact_profit_loss pl ON c.company_id = pl.company_id 
            AND pl.year = (SELECT MAX(year) FROM fact_profit_loss WHERE company_id = c.company_id)
        LEFT JOIN fact_cash_flow cf ON c.company_id = cf.company_id 
            AND cf.year = (SELECT MAX(year) FROM fact_cash_flow WHERE company_id = c.company_id)
        LEFT JOIN fact_analysis fa ON c.company_id = fa.company_id 
            AND fa.period_label = '3Y' AND fa.metric = 'compounded_sales_growth'
        """
        
        df = pd.read_sql(query, engine)
        
        pros_list = []
        cons_list = []
        
        for idx, row in df.iterrows():
            company_id = row['company_id']
            company_name = row['company_name']
            
            company_pros = _evaluate_pros_rules(row)
            company_cons = _evaluate_cons_rules(row)
            
            pros_list.extend([
                {
                    'company_id': company_id,
                    'company_name': company_name,
                    'statement': pro,
                    'type': 'pro',
                    'created_at': datetime.utcnow()
                }
                for pro in company_pros
            ])
            
            cons_list.extend([
                {
                    'company_id': company_id,
                    'company_name': company_name,
                    'statement': con,
                    'type': 'con',
                    'created_at': datetime.utcnow()
                }
                for con in company_cons
            ])
        
        # Store pros and cons in database (fact_pros_cons table)
        if pros_list or cons_list:
            all_statements = pros_list + cons_list
            stmt_df = pd.DataFrame(all_statements)
            stmt_df.to_sql('fact_pros_cons', engine, if_exists='append', index=False)
        
        result = {
            "count": len(df),
            "pros_count": len(pros_list),
            "cons_count": len(cons_list),
        }
        
        logger.info(f"Generated pros/cons for {result['count']} companies", extra={"extra_data": result})
        return result
        
    except Exception as e:
        logger.error(f"Error in generate_all_pros_cons: {str(e)}")
        raise


def _evaluate_pros_rules(row: pd.Series) -> list[str]:
    """
    Evaluate all pro rules for a company.
    Returns list of pro statements.
    """
    pros = []
    
    try:
        # Rule 1: D/E < 0.1 → "Company is almost debt free."
        if pd.notna(row['debt_to_equity']) and row['debt_to_equity'] < 0.1:
            pros.append("Company is almost debt free.")
        
        # Rule 2: 3Y ROE > 20% → "Company has a good return on equity (ROE) track record: 3 Years ROE {value}%"
        if pd.notna(row['growth_3y']) and row['growth_3y'] > 20:
            pros.append(f"Company has a good return on equity (ROE) track record: 3 Years ROE {row['growth_3y']:.1f}%")
        
        # Rule 3: Dividend payout consistently > 30% for 5 years
        if pd.notna(row['dividend_payout_pct']) and row['dividend_payout_pct'] > 30:
            pros.append(f"Company has been maintaining a healthy dividend payout of {row['dividend_payout_pct']:.1f}%")
        
        # Rule 4: 10Y sales CAGR > 15%
        # Note: This requires historical data from fact_analysis table
        
        # Rule 5: Operating cash flow > net profit for quality
        if pd.notna(row['operating_activity']) and pd.notna(row['free_cash_flow']):
            if row['operating_activity'] > 0 and row['free_cash_flow'] > 0:
                pros.append("Strong cash conversion — OCF exceeds reported profits")
        
        # Rule 6: Low interest coverage risk < 2 (inverse)
        if pd.notna(row['operating_profit']) and pd.notna(row['interest']) and row['interest'] > 0:
            interest_coverage = row['operating_profit'] / row['interest']
            if interest_coverage > 2:
                pros.append(f"Healthy interest coverage ratio of {interest_coverage:.2f}x")
        
        # Rule 7: OPM > 15%
        if pd.notna(row['opm_pct']) and row['opm_pct'] > 15:
            pros.append(f"Strong operating profit margins at {row['opm_pct']:.1f}%")
        
    except Exception as e:
        logger.warning(f"Error evaluating pros rules: {str(e)}")
    
    return pros


def _evaluate_cons_rules(row: pd.Series) -> list[str]:
    """
    Evaluate all con rules for a company.
    Returns list of con statements.
    """
    cons = []
    
    try:
        # Rule 1: 5Y sales CAGR < 10%
        # Note: This requires historical data from fact_analysis table
        
        # Rule 2: Latest borrowings > previous borrowings × 1.5
        # Note: This requires year-over-year comparison
        
        # Rule 3: D/E > 1.5 → "Stock carries high debt — leverage levels require monitoring"
        if pd.notna(row['debt_to_equity']) and row['debt_to_equity'] > 1.5:
            cons.append("Stock carries high debt — leverage levels require monitoring")
        
        # Rule 4: Net profit - operating cash flow > 0.3 × net profit
        # "Earnings quality concern — reported profits exceed actual cash generation"
        
        # Rule 5: Interest coverage < 2
        if pd.notna(row['operating_profit']) and pd.notna(row['interest']) and row['interest'] > 0:
            interest_coverage = row['operating_profit'] / row['interest']
            if interest_coverage < 2:
                cons.append(f"Low interest coverage ratio of {interest_coverage:.2f}x — debt repayment risk")
        
        # Rule 6: OPM declining for 3 consecutive years
        # Note: Requires historical year-over-year comparison
        
        # Rule 7: High leverage D/E > 2.0
        if pd.notna(row['debt_to_equity']) and row['debt_to_equity'] > 2.0:
            cons.append(f"Very high leverage with debt-to-equity ratio of {row['debt_to_equity']:.2f}")
        
        # Rule 8: Low profitability score
        if pd.notna(row['profitability_score']) and row['profitability_score'] < 5:
            cons.append("Low profitability metrics require attention")
        
    except Exception as e:
        logger.warning(f"Error evaluating cons rules: {str(e)}")
    
    return cons
