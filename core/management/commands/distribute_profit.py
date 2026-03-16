from django.core.management.base import BaseCommand
from core.models import *  # Added Transaction
from decimal import Decimal
from django.db import transaction 

class Command(BaseCommand):
    help = 'Distributes daily profit to all verified users and logs the transaction'

    def handle(self, *args, **options):
        active_profiles = InvestmentProfile.objects.filter(is_verified=True, balance__gt=0)
        
        count = 0
        
        with transaction.atomic():
            for profile in active_profiles:
                profit_amount = profile.balance * (profile.daily_roi_percentage / Decimal('100'))
                
                if profit_amount > 0:
                    profile.balance += profit_amount
                    profile.total_profit += profit_amount
                    profile.save()

                    Transaction.objects.create(
                        user=profile.user,
                        type='PROFIT',
                        amount=profit_amount,
                        description=f"Daily ROI: {profile.daily_roi_percentage}% credited"
                    )
                    count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully credited profit to {count} accounts.'))