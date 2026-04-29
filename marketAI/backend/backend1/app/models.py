from django.db import models

class DimCompany(models.Model):
    symbol = models.CharField(max_length=50, primary_key=True)
    company_name = models.CharField(max_length=255)
    company_logo = models.URLField(max_length=500, null=True, blank=True)
    website = models.URLField(max_length=500, null=True, blank=True)
    nse_url = models.URLField(max_length=500, null=True, blank=True)
    bse_url = models.URLField(max_length=500, null=True, blank=True)
    face_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    book_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    about_company = models.TextField(null=True, blank=True)
    sector_name = models.CharField(max_length=255, null=True, blank=True)
    sector_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'dim_company'

class FactProfitLoss(models.Model):
    id = models.AutoField(primary_key=True)
    symbol = models.ForeignKey(DimCompany, on_delete=models.CASCADE, db_column='symbol')
    year_id = models.IntegerField()
    sales = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    expenses = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    operating_profit = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    opm_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    other_income = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    interest = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    depreciation = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    profit_before_tax = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    tax_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    net_profit = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    eps = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    dividend_payout_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    net_profit_margin_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    expense_ratio_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    interest_coverage = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    asset_turnover = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    return_on_assets = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = 'fact_profit_loss'

class MlScore(models.Model):
    id = models.AutoField(primary_key=True)
    symbol = models.ForeignKey(DimCompany, on_delete=models.CASCADE, db_column='symbol')
    company_name = models.CharField(max_length=255, null=True, blank=True)
    sector_name = models.CharField(max_length=255, null=True, blank=True)
    computed_at = models.DateTimeField()
    overall_score = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    profitability_score = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    growth_score = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    leverage_score = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cashflow_score = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    dividend_score = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    trend_score = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    health_label = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'ml_scores'

