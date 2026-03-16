from django.core.management.base import BaseCommand
from decimal import Decimal

# DO NOT import models here at the top. 
# This is what causes the "already registered" warning.

class Command(BaseCommand):
    help = 'Adds 1% daily ROI'

    def handle(self, *args, **options):
        # Import ONLY inside the handle method
        from core.models import InvestmentProfile
        
        profiles = InvestmentProfile.objects.filter(balance__gt=0)
        
        if not profiles.exists():
            self.stdout.write(self.style.WARNING("No active profiles with a balance found."))
            return

        count = 0
        for profile in profiles:
            profit = profile.balance * Decimal('0.01')
            profile.balance += profit
            profile.total_profit += profit
            profile.save()
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f'Processed {count} accounts.'))