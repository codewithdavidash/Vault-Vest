from django.db import transaction as db_transaction
import uuid
from django.contrib.auth import get_user_model
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.apps import apps 
from datetime import timedelta
import random
import string


@receiver(post_save, sender=User)
def manage_user_profile(sender, instance, created, **kwargs):
    if created:
        InvestmentProfile.objects.create(user=instance)
    else:
        # Check if profile exists before saving to avoid errors
        if hasattr(instance, 'investment_profile'):
            instance.investment_profile.save()

# --- MODELS ---

class InvestmentProfile(models.Model):
    KYC_STATUS = [
        ('UNSUBMITTED', 'Unsubmitted'),
        ('PENDING', 'Pending Review'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
    ]
    ID_TYPES = [
        ('DL', 'Drivers License'),
        ('PP', 'Passport'),
        ('ID', 'National ID')
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='investment_profile')
    balance = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    total_profit = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    settlement_address = models.CharField(max_length=255, blank=True, null=True)
    daily_roi_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.50) # 0.5% daily
    last_roi_date = models.DateField(null=True, blank=True)
    # KYC & Personal Fields
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    ssn_number = models.CharField(max_length=15, blank=True, null=True, verbose_name="SSN/Tax ID")
    id_type = models.CharField(max_length=50, choices=ID_TYPES, default='DL')
    is_verified = models.BooleanField(default=False)
    kyc_status = models.CharField(max_length=20, choices=KYC_STATUS, default='UNSUBMITTED')
    
    # ID Uploads
    id_front = models.ImageField(upload_to='kyc_docs/%Y/%m/%d/', blank=True, null=True)
    id_back = models.ImageField(upload_to='kyc_docs/%Y/%m/%d/', blank=True, null=True)
    
    date_verified = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    daily_roi_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.50) # 0.5% daily
    def save(self, *args, **kwargs):
        # Auto-verify logic
        if self.kyc_status == 'VERIFIED' and not self.is_verified:
            self.is_verified = True
            self.date_verified = timezone.now()
        elif self.kyc_status != 'VERIFIED':
            self.is_verified = False
            self.date_verified = None
        super().save(*args, **kwargs)

    def kyc_directory_path(instance, filename):
        return f'kyc/user_{instance.user.id}/{filename}'


    def __str__(self):
        return f"{self.user.username}'s Vault"


class Deposit(models.Model):
    METHOD_CHOICES = [
        ('CRYPTO', 'Cryptocurrency'),
        ('GIFT_CARD', 'Gift Card Asset'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'), 
        ('COMPLETED', 'Success'), 
        ('FAILED', 'Declined')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposits')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    card_details = models.TextField(blank=True, null=True, help_text="Enter Gift Card Code/PIN here")
    proof_image = models.ImageField(upload_to='proofs/%Y/%m/%d/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # NEW: Safety Lock
    is_credited = models.BooleanField(default=False, editable=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk: # Only run on updates
            old_instance = Deposit.objects.get(pk=self.pk)
            
            # If status changed to COMPLETED and hasn't been credited yet
            if old_instance.status != 'COMPLETED' and self.status == 'COMPLETED' and not self.is_credited:
                with db_transaction.atomic():
                    profile = self.user.investment_profile
                    profile.balance += self.amount
                    profile.save()

                    self.is_credited = True
                    
                    # Link the Ledger
                    Transaction.objects.create(
                        user=self.user,
                        type='DEPOSIT',
                        gateway=self.method,
                        amount=self.amount,
                        status='COMPLETED',
                        admin_notes=f"System: Deposit approved via {self.get_method_display()}"
                    )
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.username} - ${self.amount} ({self.status})"


class Withdrawal(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=12, decimal_places=2) 
    fee_charged = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    address = models.CharField(max_length=255)
    
    # NEW: The Payout Reference
    transaction_hash = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="Paste the blockchain TXID or payment reference here"
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    is_refunded = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk:
            old_instance = Withdrawal.objects.get(pk=self.pk)
            
            # Refund Logic for Rejected requests
            if old_instance.status == 'PENDING' and self.status == 'REJECTED' and not self.is_refunded:
                profile = self.user.investment_profile
                total_to_refund = self.amount + self.fee_charged
                profile.balance += total_to_refund
                profile.save()
                self.is_refunded = True
                
                Transaction = apps.get_model('core', 'Transaction') 
                Transaction.objects.create(
                    user=self.user,
                    type='REFUND',
                    amount=total_to_refund,
                    status='COMPLETED',
                    description=f"Refund: Withdrawal rejected."
                )
        
        super().save(*args, **kwargs)
    

class SupportTicket(models.Model):
    CATEGORY_CHOICES = [
        ('WITHDRAWAL', 'Withdrawal Issue'),
        ('DEPOSIT', 'Deposit Issue'),
        ('KYC', 'Identity Verification'),
        ('ACCOUNT', 'Account Settings'),
        ('OTHER', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('PENDING', 'Pending Admin'),
        ('CLOSED', 'Closed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ticket_id = models.CharField(max_length=12, unique=True, editable=False)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            self.ticket_id = f"TIC-{timezone.now().strftime('%y%m%d')}-{random.randint(1000, 9999)}"
        super().save(*args, **kwargs)
    

User = get_user_model()


class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('PROFIT', 'Profit'),
        ('BONUS', 'Bonus'),
    )
    
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )

    GATEWAY_CHOICES = (
        ('CRYPTO', 'Cryptocurrency'),
        ('GIFTCARD', 'Giftcard'),
        ('INTERNAL', 'Internal Transfer'),
    )

    # 1. Identification
    # Ensure this is inside the model class properly
    reference_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True) 
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transactions")
    
    # 2. Financial Info
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default='INTERNAL')
    amount = models.DecimalField(max_digits=20, decimal_places=2) # Bumped to 20 for extreme scale
    
    # 3. Crypto Specifics
    crypto_currency = models.CharField(max_length=10, blank=True, null=True, help_text="e.g., BTC, USDT, ETH")
    wallet_address = models.CharField(max_length=255, blank=True, null=True)
    transaction_hash = models.CharField(max_length=255, blank=True, null=True, help_text="Blockchain TXID")
    
    # 4. Giftcard Specifics
    card_type = models.CharField(max_length=50, blank=True, null=True, help_text="e.g., Amazon, Apple")
    card_code = models.CharField(max_length=100, blank=True, null=True) 
    
    # 5. Proof & Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    receipt = models.ImageField(upload_to='receipts/%Y/%m/', blank=True, null=True)
    admin_notes = models.TextField(blank=True, null=True, help_text="Internal feedback for the user")
    
    timestamp = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['reference_id']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.user.username} | {self.type} | {self.amount} ({self.status})"
    
    
class WithdrawalVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # Store data as JSON so we don't create the Withdrawal object until verified
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    address = models.CharField(max_length=255)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        # Code expires after 10 minutes
        return not self.is_used and timezone.now() < self.created_at + timedelta(minutes=10)

    @staticmethod
    def generate_code():
        return ''.join(random.choices(string.digits, k=6))


class TicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='replies')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    is_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']