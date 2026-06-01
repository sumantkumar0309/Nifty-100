from rest_framework import serializers
from .models import DimCompany, FactProfitLoss, MlScore

class DimCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = DimCompany
        fields = '__all__'

class FactProfitLossSerializer(serializers.ModelSerializer):
    class Meta:
        model = FactProfitLoss
        fields = '__all__'

class MlScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = MlScore
        fields = '__all__'

