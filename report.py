import pandas as pd
companies = pd.read_csv('data/clean/dim_company.csv')['symbol'].unique()
pl = pd.read_csv('data/clean/fact_profit_loss.csv')
cf = pd.read_csv('data/clean/fact_cash_flow.csv')
missing_pl = pl[~pl['symbol'].isin(companies)]['symbol'].unique()
missing_cf = cf[~cf['symbol'].isin(companies)]['symbol'].unique()
print(f"Symbols dropped in profit_loss: {', '.join(missing_pl)}")
print(f"Symbols dropped in cash_flow: {', '.join(missing_cf)}")

