from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import InvestmentProfile, Transaction
from django.utils import timezone
from decimal import Decimal

class Command(BaseCommand):
    help = 'Calculates and adds daily ROI to all user balances'

    def handle(self, *args, **options):
        # 1. Fetch profiles that actually have money
        profiles = InvestmentProfile.objects.filter(balance__gt=0)
        count = 0
        today = timezone.now().date()

        # 2. Use atomic transaction so if one fails, none are processed
        with transaction.atomic():
            for profile in profiles:
                # Check if we already paid this user today to prevent double payouts
                if profile.last_roi_date == today:
                    continue 

                # 3. Calculate profit (e.g., 0.5% of $1000 = $5)
                # Ensure daily_roi_percentage is treated as a Decimal
                roi_rate = Decimal(str(profile.daily_roi_percentage)) / Decimal('100')
                daily_profit = profile.balance * roi_rate
                
                if daily_profit > 0:
                    # 4. Update Profile
                    profile.balance += daily_profit
                    profile.total_profit += daily_profit
                    profile.last_roi_date = today
                    profile.save()

                    # 5. Record in Ledger
                    # Using 'admin_notes' since 'description' wasn't in your Transaction model
                    Transaction.objects.create(
                        user=profile.user,
                        type='PROFIT',
                        amount=daily_profit,
                        status='COMPLETED',
                        gateway='INTERNAL',
                        admin_notes=f"Daily ROI Profit ({profile.daily_roi_percentage}%)"
                    )
                    count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully processed ROI for {count} users.'))