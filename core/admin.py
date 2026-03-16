from django.contrib import admin, messages
from django.db.models import Sum
from .models import *
from django.utils.html import format_html


@admin.action(description="Reject selected deposits")
def reject_deposits(self, request, queryset):
    pending_queryset = queryset.filter(status='PENDING')
    count = pending_queryset.count()
    for deposit in pending_queryset:
        deposit.status = 'FAILED'
        deposit.save() # Triggers any custom save logic
    self.message_user(request, f"Rejected {count} deposits.", messages.WARNING)


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('user', 'formatted_amount', 'method', 'colored_status', 'proof_link', 'created_at')
    list_filter = ('status', 'method', 'created_at')
    search_fields = ('user__username', 'card_details', 'amount')
    actions = ['approve_deposits', 'reject_deposits']    
    
    readonly_fields = ('is_credited', 'preview_proof', 'created_at')
    
    fieldsets = (
        ('User & Status', {
            'fields': ('user', 'status', 'is_credited', 'created_at')
        }),
        ('Payment Info', {
            'fields': ('amount', 'method', 'card_details'),
        }),
        ('Verification', {
            'fields': ('proof_image', 'preview_proof'),
        }),
    )

    # --- ACTIONS LOGIC ---

    @admin.action(description="Approve and Fund selected deposits")
    def approve_deposits(self, request, queryset):
        # Filter only pending to prevent double-processing logic
        pending_queryset = queryset.filter(status='PENDING')
        count = pending_queryset.count()
        
        for deposit in pending_queryset:
            deposit.status = 'COMPLETED'
            # .save() is called on each to trigger the logic in your Model's save() method
            deposit.save() 
            
        self.message_user(request, f"Successfully approved {count} deposits.", messages.SUCCESS)

    @admin.action(description="Reject selected deposits")
    def reject_deposits(self, request, queryset):
        updated = queryset.filter(status='PENDING').update(status='FAILED')
        self.message_user(request, f"Rejected {updated} deposits.", messages.WARNING)

    # --- HELPER METHODS ---

    def formatted_amount(self, obj):
        return format_html('<b>${}</b>', obj.amount)
    formatted_amount.short_description = 'Amount'

    def colored_status(self, obj):
        colors = {
            'PENDING': '#ffc107',  
            'COMPLETED': '#198754', 
            'FAILED': '#dc3545',    
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 10px; border-radius: 10px; font-weight: bold;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display()
        )
    colored_status.short_description = 'Status'

    def proof_link(self, obj):
        if obj.proof_image:
            return format_html('<a href="{}" target="_blank">View Receipt ↗</a>', obj.proof_image.url)
        return "No Proof"
    proof_link.short_description = 'Action'

    def preview_proof(self, obj):
        if obj.proof_image:
            return format_html(
                '<div style="margin-top: 10px;">'
                '<img src="{}" style="max-width: 500px; border: 3px solid #ccc; border-radius: 15px;"/>'
                '</div>', 
                obj.proof_image.url
            )
        return "No proof image uploaded by user."
    preview_proof.short_description = 'Proof Image Preview'


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'address', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'address')
    actions = ['mark_as_completed', 'mark_as_rejected']

    @admin.action(description="💰 Mark as Paid (Completed)")
    def mark_as_completed(self, request, queryset):
        # We don't need to change balance here (it was deducted at request)
        updated = queryset.filter(status='PENDING').update(status='COMPLETED')
        self.message_user(request, f"Successfully marked {updated} withdrawals as paid.")

    @admin.action(description="🔄 Reject & Refund User")
    def mark_as_rejected(self, request, queryset):
        count = 0
        for withdrawal in queryset.filter(status='PENDING'):
            withdrawal.status = 'REJECTED'
            withdrawal.save() # This triggers the refund logic in the model's save()
            count += 1
        
        if count > 0:
            self.message_user(request, f"Rejected {count} withdrawals. Funds have been returned to user balances.")
        else:
            self.message_user(request, "No pending withdrawals were selected.", level='warning')


@admin.register(InvestmentProfile)
class InvestmentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'total_profit', 'kyc_status', 'is_verified')
    list_filter = ('kyc_status', 'is_verified')
    search_fields = ('user__username', 'user__email')
    
    # 1. These must match the function names below
    readonly_fields = ('id_front_preview', 'id_back_preview')

    # 2. THE PREVIEW FUNCTIONS (Must be inside the class)
    def id_front_preview(self, obj):
        if obj.id_front:
            return format_html('<img src="{}" style="width: 300px; border-radius: 10px; border: 1px solid #ddd;" />', obj.id_front.url)
        return "No front image uploaded"
    id_front_preview.short_description = "ID Front Side"

    def id_back_preview(self, obj):
        if obj.id_back:
            return format_html('<img src="{}" style="width: 300px; border-radius: 10px; border: 1px solid #ddd;" />', obj.id_back.url)
        return "No back image uploaded"
    id_back_preview.short_description = "ID Back Side"

    # 3. THE SYSTEM OVERVIEW LOGIC
    def changelist_view(self, request, extra_context=None):
        stats = InvestmentProfile.objects.aggregate(
            total_liabilities=Sum('balance'),
            total_payouts=Sum('total_profit')
        )
        
        pending_kyc = InvestmentProfile.objects.filter(kyc_status='PENDING').count()
        pending_deposits = Deposit.objects.filter(status='PENDING').count()
        pending_withdrawals = Withdrawal.objects.filter(status='PENDING').count()

        extra_context = extra_context or {}
        extra_context['summary_stats'] = {
            'liabilities': stats['total_liabilities'] or 0,
            'payouts': stats['total_payouts'] or 0,
            'kyc': pending_kyc,
            'deposits': pending_deposits,
            'withdrawals': pending_withdrawals,
        }
        return super().changelist_view(request, extra_context=extra_context)
    

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('user', 'subject', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'subject')
    

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    # Main list view
    list_display = ('user', 'type_badge', 'colored_amount', 'status_badge', 'gateway', 'timestamp', 'receipt_preview')
    list_filter = ('status', 'type', 'gateway', 'timestamp')
    search_fields = ('user__username', 'reference_id', 'card_code', 'wallet_address')
    
    # Fields that you (the admin) can edit
    # We remove 'status' from readonly so you can change it to COMPLETED
    readonly_fields = ('user', 'type', 'amount', 'gateway', 'crypto_currency', 
                       'wallet_address', 'transaction_hash', 'card_type', 
                       'card_code', 'timestamp', 'updated_at')

    fieldsets = (
        ('Verification Control', {
            'fields': ('status', 'admin_notes'),
            'description': 'Change status to COMPLETED to trigger balance updates via signals.',
        }),
        ('Transaction Info', {
            'fields': ('user', 'type', 'amount', 'gateway', 'timestamp'),
        }),
        ('Asset Details (Giftcard/Crypto)', {
            'fields': ('card_type', 'card_code', 'crypto_currency', 'wallet_address', 'transaction_hash', 'receipt'),
        }),
    )

    # --- Custom Badges ---

    def type_badge(self, obj):
        colors = {
            'DEPOSIT': '#4f46e5',    # Indigo
            'WITHDRAWAL': '#ef4444', # Red
            'PROFIT': '#10b981',     # Emerald
            'BONUS': '#8b5cf6',      # Violet
        }
        return format_html(
            '<span style="background: {0}; color: white; padding: 4px 10px; border-radius: 8px; font-size: 10px; font-weight: 800; text-transform: uppercase;">{1}</span>',
            colors.get(obj.type, '#64748b'),
            obj.type
        )
    type_badge.short_description = 'Type'

    def status_badge(self, obj):
        colors = {
            'PENDING': '#f59e0b',    # Amber
            'COMPLETED': '#10b981',  # Emerald
            'FAILED': '#64748b',     # Slate
            'PROCESSING': '#3b82f6', # Blue
        }
        return format_html(
            '<span style="color: {0}; font-weight: 800; font-size: 11px;">● {1}</span>',
            colors.get(obj.status, '#64748b'),
            obj.status
        )
    status_badge.short_description = 'Status'

    def colored_amount(self, obj):
        color = "#10b981" if obj.type != 'WITHDRAWAL' else "#ef4444"
        prefix = "-" if obj.type == 'WITHDRAWAL' else "+"
        return format_html(
            '<span style="color: {0}; font-weight: bold; font-family: monospace;">{1}${2}</span>',
            color, prefix, obj.amount
        )
    colored_amount.short_description = 'Amount'

    def receipt_preview(self, obj):
        if obj.receipt:
            return format_html('<img src="{}" style="width: 40px; height: 40px; border-radius: 6px; object-fit: cover;" />', obj.receipt.url)
        if obj.card_code:
            return format_html('<span title="{}" style="cursor:help;">💳 Card</span>', obj.card_code)
        return "-"
    receipt_preview.short_description = 'Media'

    # --- Actions ---
    
    actions = ['mark_as_completed']

    def mark_as_completed(self, request, queryset):
        updated = queryset.filter(status__in=['PENDING', 'PROCESSING']).update(status='COMPLETED')
        self.message_user(request, f"{updated} transactions completed. Balances updated.", messages.SUCCESS)
    mark_as_completed.short_description = "✅ Bulk Approve Selected"