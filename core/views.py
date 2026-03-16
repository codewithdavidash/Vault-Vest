from django.db import transaction as db_transaction
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.db.models import Sum
from django.contrib import messages
from .forms import *
from .models import *
from datetime import timedelta
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from django.shortcuts import get_object_or_404
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from django.core.mail import send_mail


@login_required
def create_deposit(request):
    if request.method == 'POST':
        form = DepositForm(request.POST, request.FILES)
        if form.is_valid():
            deposit = form.save(commit=False)
            deposit.user = request.user
            deposit.type = 'DEPOSIT'
            deposit.status = 'PENDING'  # Force pending for manual admin review
            deposit.save()
            return redirect('dashboard')
    else:
        form = DepositForm()
    
    return render(request, 'core/deposit_form.html', {'form': form})

@login_required
def ticket_detail(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, ticket_id=ticket_id, user=request.user)
    
    if request.method == "POST":
        message_text = request.POST.get('message')
        if message_text:
            TicketMessage.objects.create(
                ticket=ticket,
                sender=request.user,
                message=message_text,
                is_admin=False
            )
            # Optional: Set status back to OPEN if user replies
            ticket.status = 'OPEN'
            ticket.save()
            messages.success(request, "Reply sent.")
            return redirect('ticket_detail', ticket_id=ticket.ticket_id)

    replies = ticket.replies.all()
    return render(request, 'core/support_detail.html', {
        'ticket': ticket,
        'replies': replies
    })

@login_required
def support_view(request):
    if request.method == "POST":
        category = request.POST.get('category')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        
        SupportTicket.objects.create(
            user=request.user,
            category=category,
            subject=subject,
            message=message
        )
        messages.success(request, "Ticket submitted. Our team will contact you shortly.")
        return redirect('support')

    tickets = SupportTicket.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'core/support.html', {'tickets': tickets})

@login_required
def resend_withdrawal_code(request, verification_id):
    verification = get_object_or_404(WithdrawalVerification, id=verification_id, user=request.user)
    
    # Senior Dev Move: Rate Limiting
    # Check if the last code was sent less than 60 seconds ago
    elapsed_time = timezone.now() - verification.created_at
    if elapsed_time.total_seconds() < 60:
        messages.warning(request, "Please wait before requesting a new code.")
        return redirect('verify_withdrawal', verification_id=verification.id)

    # Generate new code and update timestamp
    new_code = WithdrawalVerification.generate_code()
    verification.code = new_code
    verification.created_at = timezone.now()
    verification.save()

    # Send the new email
    send_mail(
        'New Verification Code',
        f'Your new withdrawal verification code is {new_code}.',
        'noreply@yourplatform.com',
        [request.user.email],
        fail_silently=False,
    )

    messages.success(request, "A new code has been sent to your email.")
    return redirect('verify_withdrawal', verification_id=verification.id)

@login_required
def verify_withdrawal(request, verification_id):
    verification = get_object_or_404(WithdrawalVerification, id=verification_id, user=request.user)
    
    if request.method == "POST":
        input_code = request.POST.get('code')
        
        if verification.is_valid() and input_code == verification.code:
            # SUCCESS LOGIC START
            profile = request.user.investment_profile
            
            # Final check to prevent race conditions
            if profile.balance >= verification.amount:
                # 1. Create the real Withdrawal
                withdrawal = Withdrawal.objects.create(
                    user=request.user,
                    amount=verification.amount,
                    address=verification.address,
                    status='PENDING'
                )
                
                # 2. Deduct Balance
                profile.balance -= verification.amount
                profile.save()
                
                # 3. Mark verification as used
                verification.is_used = True
                verification.save()
                
                messages.success(request, "Withdrawal initiated successfully!")
                return redirect('withdrawal_history')
            # SUCCESS LOGIC END
            
        messages.error(request, "Invalid or expired code.")
    
    return render(request, 'core/verify_code.html', {'verification': verification})

@login_required
def initiate_withdrawal(request):
    if request.method == "POST":
        amount = request.POST.get('amount')
        address = request.POST.get('address')
        
        # 1. Check if user has enough balance
        if request.user.investment_profile.balance < Decimal(amount):
            messages.error(request, "Insufficient balance.")
            return redirect('withdraw')

        # 2. Generate and Save Verification
        code = WithdrawalVerification.generate_code()
        verify_obj = WithdrawalVerification.objects.create(
            user=request.user,
            amount=amount,
            address=address,
            code=code
        )

        # 3. Send Email (Tailwind styled in your head!)
        send_mail(
            'Withdrawal Verification Code',
            f'Your code is {code}. It expires in 10 minutes.',
            'noreply@yvaultvest.com',
            [request.user.email],
            fail_silently=False,
        )

        # Redirect to a page to enter the code
        return redirect('verify_withdrawal', verification_id=verify_obj.id)

@login_required
def download_withdrawal_pdf(request, withdrawal_id):
    withdrawal = get_object_or_404(Withdrawal, id=withdrawal_id, user=request.user)
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Receipt_{withdrawal.id}.pdf"'

    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter
    
    # --- CONSTANTS & BRANDING ---
    brand_color = colors.HexColor("#1e293b")  # Dark Slate (Tailwind style)
    accent_color = colors.HexColor("#4f46e5") # Indigo
    text_muted = colors.HexColor("#64748b")
    
    # --- HEADER SECTION ---
    # Draw a top accent bar
    p.setFillColor(brand_color)
    p.rect(0, height - 1.2 * inch, width, 1.2 * inch, fill=1, stroke=0)
    
    # White Title over the dark bar
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 22)
    p.drawString(0.8 * inch, height - 0.75 * inch, "TRANSACTION RECEIPT")
    
    p.setFont("Helvetica", 10)
    p.drawString(0.8 * inch, height - 1.0 * inch, f"GENERATED ON: {withdrawal.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # --- BODY SECTION ---
    p.setFillColor(colors.black)
    y = height - 1.8 * inch
    
    # Metadata Row (ID & Status)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(0.8 * inch, y, "TRANSACTION ID")
    p.drawString(4.5 * inch, y, "STATUS")
    
    y -= 0.25 * inch
    p.setFont("Helvetica", 11)
    p.setFillColor(text_muted)
    p.drawString(0.8 * inch, y, f"WID-{withdrawal.id:06d}") # Zero-padded ID looks more "bank-like"
    
    # Status styling
    status_text = withdrawal.get_status_display().upper()
    if status_text == "COMPLETED":
        p.setFillColor(colors.HexColor("#059669")) # Emerald Green
    else:
        p.setFillColor(colors.HexColor("#d97706")) # Amber
    p.drawString(4.5 * inch, y, status_text)

    # --- HORIZONTAL DIVIDER ---
    y -= 0.4 * inch
    p.setStrokeColor(colors.HexColor("#e2e8f0"))
    p.line(0.8 * inch, y, 7.7 * inch, y)

    # --- FINANCIALS TABLE ---
    y -= 0.5 * inch
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 13)
    p.drawString(0.8 * inch, y, "Financial Summary")
    
    y -= 0.4 * inch
    
    # Table Headings
    p.setFont("Helvetica-Bold", 10)
    p.setFillColor(text_muted)
    p.drawString(0.8 * inch, y, "DESCRIPTION")
    p.drawRightString(7.7 * inch, y, "AMOUNT")
    
    # Line Items
    y -= 0.3 * inch
    p.setFillColor(colors.black)
    p.setFont("Helvetica", 11)
    
    # Gross Amount (Calculated)
    gross = withdrawal.amount + withdrawal.fee_charged
    p.drawString(0.8 * inch, y, "Requested Amount")
    p.drawRightString(7.7 * inch, y, f"${gross:,.2f}")
    
    y -= 0.3 * inch
    p.drawString(0.8 * inch, y, "Service Fee")
    p.drawRightString(7.7 * inch, y, f"- ${withdrawal.fee_charged:,.2f}")
    
    # Total Box
    y -= 0.5 * inch
    p.setFillColor(colors.HexColor("#f8fafc"))
    p.rect(0.8 * inch, y - 0.2 * inch, 6.9 * inch, 0.5 * inch, fill=1, stroke=0)
    
    p.setFillColor(brand_color)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(1.0 * inch, y, "NET DISBURSED")
    p.drawRightString(7.5 * inch, y, f"${withdrawal.amount:,.2f}")

    # --- WALLET & HASH ---
    y -= 1.0 * inch
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(0.8 * inch, y, "DESTINATION DETAILS")
    
    y -= 0.3 * inch
    p.setFont("Helvetica", 10)
    p.setFillColor(text_muted)
    p.drawString(0.8 * inch, y, "Wallet Address:")
    p.setFillColor(colors.black)
    p.setFont("Courier", 10) # Monospaced for wallet
    p.drawString(2.2 * inch, y, withdrawal.address)
    
    if withdrawal.transaction_hash:
        y -= 0.25 * inch
        p.setFont("Helvetica", 10)
        p.setFillColor(text_muted)
        p.drawString(0.8 * inch, y, "Transaction Hash:")
        p.setFillColor(accent_color)
        p.setFont("Courier", 9)
        p.drawString(2.2 * inch, y, withdrawal.transaction_hash)

    # --- FOOTER ---
    p.setStrokeColor(brand_color)
    p.setLineWidth(2)
    p.line(0.8 * inch, 1.2 * inch, 1.5 * inch, 1.2 * inch) # Short accent line
    
    p.setFillColor(text_muted)
    p.setFont("Helvetica-Oblique", 9)
    p.drawString(0.8 * inch, 1.0 * inch, "This document serves as an official proof of transaction.")
    p.drawString(0.8 * inch, 0.85 * inch, "For support, please contact help@yourplatform.com")

    p.showPage()
    p.save()
    return response


@login_required
def dashboard(request):
    # 1. Secure Profile Fetch
    profile, _ = InvestmentProfile.objects.get_or_create(user=request.user)
    
    # 2. Status Tracker: Get the most recent active deposit
    # We fetch this so the progress bar in your dashboard actually works
    recent_deposit = Deposit.objects.filter(user=request.user).exclude(status='FAILED').order_by('-created_at').first()
    
    # 3. Transaction History (Limit to 7 for a cleaner chart/table balance)
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')[:7]
    
    # 4. Financial Analytics (Growth Curve)
    chart_labels, chart_data = [], []
    today = timezone.now().date()
    roi_factor = float(profile.daily_roi_percentage or 0) / 100
    current_bal = float(profile.balance)

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        chart_labels.append(day.strftime('%a'))
        # Formula: P = A / (1 + r)^n
        past_val = current_bal / (1 + roi_factor)**i
        chart_data.append(round(max(past_val, 0), 2))

    # 5. Summary Stats calculations
    total_deposited = Deposit.objects.filter(
        user=request.user, 
        status='COMPLETED'
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    daily_yield = profile.balance * (Decimal(str(profile.daily_roi_percentage or 0)) / Decimal('100'))

    return render(request, 'core/dashboard.html', {
        'profile': profile,
        'transactions': transactions,
        'recent_deposit': recent_deposit,  # Necessary for the tracker!
        'total_deposited': total_deposited,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'daily_yield': daily_yield,
    })
    
        
def index(request):
    context = {
        'market_data': {'btc_price': '64,210.40', 'eth_price': '3,450.12'},
        'stats': {'total_invested': '2.4M', 'active_users': '15k+'},
        'is_home': True
    }
    return render(request, 'core/index.html', context)

@login_required
def logoutView(request):
    logout(request)
    return redirect('login')

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Profile is auto-created by Signals in models.py, 
            # but get_or_create here is a safe secondary check.
            InvestmentProfile.objects.get_or_create(user=user)
            login(request, user)
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'auth/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(request, 
                                username=form.cleaned_data.get('username'), 
                                password=form.cleaned_data.get('password'))
            if user:
                login(request, user)
                return redirect('dashboard')
            messages.error(request, "Invalid credentials.")
    else:
        form = LoginForm()
    return render(request, 'auth/login.html', {'form': form})

@login_required
def settings_view(request):
    # Using underscore to match the related_name
    profile, _ = InvestmentProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated.")
            return redirect('settings')
    else:
        form = ProfileUpdateForm(instance=profile)
    return render(request, 'core/settings.html', {'form': form, 'profile': profile})

@login_required
def kyc_upload(request):
    profile, _ = InvestmentProfile.objects.get_or_create(user=request.user)
    
    # 1. Early exit for verified users
    if profile.kyc_status == 'VERIFIED':
        return redirect('dashboard')

    if request.method == 'POST':
        id_front = request.FILES.get('id_front')
        id_back = request.FILES.get('id_back')

        # 2. Basic validation
        if id_front and id_back:
            profile.id_front = id_front
            profile.id_back = id_back
            profile.kyc_status = 'PENDING'
            profile.save()
            
            messages.success(request, "Documents submitted for review.")
            return redirect('dashboard')
        
        # 3. Targeted error message
        messages.error(request, "Please provide both the front and back images of your ID.")

    return render(request, 'core/kyc.html', {'profile': profile})

@staff_member_required
def admin_overview(request):
    stats = {
        'total_users': User.objects.count(),
        'total_deposited': Deposit.objects.filter(status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or 0,
        'active_balances': InvestmentProfile.objects.aggregate(Sum('balance'))['balance__sum'] or 0,
        'pending_withdrawals': Withdrawal.objects.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0,
    }
    return render(request, 'core/admin_overview.html', {'stats': stats})


@login_required
def transaction_history(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')
    return render(request, 'core/transactions.html', {'transactions': transactions})


@login_required
def request_withdrawal(request):
    profile = request.user.investment_profile
    MIN_WITHDRAWAL = Decimal('10.00') 
    FEE_PERCENTAGE = Decimal('0.05') # 5% Fee

    if request.method == 'POST':
        amount_str = request.POST.get('amount')
        address = request.POST.get('address')
        
        try:
            # This is the total amount to be deducted from the user's balance
            gross_amount = Decimal(amount_str)
        except (TypeError, ValueError):
            messages.error(request, "Please enter a valid numeric amount.")
            return redirect('request_withdrawal')

        # --- CALCULATIONS ---
        withdrawal_fee = gross_amount * FEE_PERCENTAGE
        net_payout = gross_amount - withdrawal_fee

        # --- VALIDATION CHECKS ---
        if profile.kyc_status != 'VERIFIED':
            messages.error(request, "Your account must be VERIFIED before you can withdraw.")
        
        elif gross_amount < MIN_WITHDRAWAL:
            messages.error(request, f"The minimum withdrawal amount is ${MIN_WITHDRAWAL}.")
            
        elif gross_amount > profile.balance:
            messages.error(request, "Insufficient balance.")
            
        else:
            # 1. Deduct the full Gross Amount from balance
            profile.balance -= gross_amount
            profile.save()

            # 2. Create Withdrawal (Stores net_payout so you know exactly what to send)
            Withdrawal.objects.create(
                user=request.user,
                amount=net_payout,
                address=address,
                status='PENDING',
                # Assuming you added a fee field to your model earlier
                # fee_charged=withdrawal_fee 
            )

            # 3. Create Transaction Ledger Entry
            Transaction.objects.create(
                user=request.user,
                type='WITHDRAWAL',
                amount=gross_amount,
                status='PENDING',
                description=f"Withdrawal to {address} (Fee: ${withdrawal_fee})"
            )

            messages.success(request, f"Request for ${net_payout} (after ${withdrawal_fee} fee) submitted.")
            return redirect('withdrawal_success')

    return render(request, 'core/withdraw.html', {
        'profile': profile, 
        'min_limit': MIN_WITHDRAWAL,
        'fee_percent': FEE_PERCENTAGE * 100 # Passes '5' to the template
    })
    

def withdrawal_success(request):
    return render(request, 'core/withdrawal_success.html')


@login_required
def unified_deposit(request):
    WALLETS = {
        'BTC': {'address': 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0w7h', 'network': 'Bitcoin'},
        'ETH': {'address': '0x71C7656EC7ab88b098defB751B7401B5f6d8976F', 'network': 'Ethereum (ERC20)'},
        'USDT': {'address': 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t', 'network': 'TRON (TRC20)'},
    }
    GIFT_CARDS = ['Amazon', 'Steam', 'Razor Gold', 'Apple/iTunes', 'Google Play']

    if request.method == 'POST':
        # Use .get() with a default to avoid NULL constraint errors
        gateway_type = request.POST.get('method', 'CRYPTO') 
        amount_str = request.POST.get('amount', '0')
        
        try:
            amount = Decimal(amount_str)
            if amount <= 0: raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, "Please enter a valid amount greater than 0.")
            return redirect('unified_deposit')

        # Determine the final "Method" string for the DB
        crypto_type = request.POST.get('crypto_type', 'BTC')
        final_method = f"{gateway_type} ({crypto_type})" if gateway_type == 'CRYPTO' else "GIFTCARD"

        # 1. Create the Deposit record with atomic safety
        try:
            with db_transaction.atomic():
                deposit = Deposit.objects.create(
                    user=request.user,
                    amount=amount,
                    method=final_method, # This will no longer be NULL
                    proof_image=request.FILES.get('proof_image'),
                    status='PENDING'
                )
                
                admin_note = ""
                if gateway_type == 'GIFTCARD':
                    card_type = request.POST.get('card_type', 'Unknown')
                    card_code = request.POST.get('card_code', 'N/A')
                    deposit.card_details = f"Type: {card_type} | Code: {card_code}"
                    deposit.save()
                    admin_note = f"Giftcard: {card_type} submission."
                else:
                    admin_note = f"Crypto: {crypto_type} deposit pending verification."

                # 2. Create the Ledger Transaction
                Transaction.objects.create(
                    user=request.user,
                    type='DEPOSIT',
                    gateway=gateway_type,
                    amount=amount,
                    status='PENDING',
                    admin_notes=admin_note
                )

            messages.success(request, "Asset submitted! Verification usually takes 10-30 minutes.")
            return redirect('transaction_history')
            
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            return redirect('unified_deposit')

    return render(request, 'core/deposit.html', {
        'wallets': WALLETS,
        'gift_cards': GIFT_CARDS
    })