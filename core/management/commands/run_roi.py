from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from core.models import InvestmentProfile, Transaction

class Command(BaseCommand):
    help = 'Calculates and adds daily ROI to verified user balances'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        
        # 1. Get all verified users who haven't received ROI today
        # We exclude users where last_roi_date == today to prevent double-paying
        active_profiles = InvestmentProfile.objects.filter(
            is_verified=True, 
            balance__gt=0
        ).exclude(last_roi_date=today)

        count = 0
        for profile in active_profiles:
            # 2. Calculate profit: (Balance * ROI%) / 100
            daily_profit = (profile.balance * profile.daily_roi_percentage) / Decimal('100.00')

            if daily_profit > 0:
                # 3. Update Profile
                profile.balance += daily_profit
                profile.total_profit += daily_profit
                profile.last_roi_date = today
                profile.save()

                # 4. Create Ledger Entry
                Transaction.objects.create(
                    user=profile.user,
                    type='PROFIT',
                    amount=daily_profit,
                    status='COMPLETED',
                    description=f"Daily ROI of {profile.daily_roi_percentage}% credited."
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully processed ROI for {count} users.'))