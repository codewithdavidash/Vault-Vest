from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    
    # Core Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # KYC and Support
    path('kyc-upload/', views.kyc_upload, name='kyc_upload'),
    path('support/', views.support_view, name='support'),

    # Withdrawal System (New 2FA Flow)
    # path('withdraw/history/', views.withdrawal_history, name='withdrawal_history'),
    path('withdraw/request/', views.initiate_withdrawal, name='request_withdrawal'),
    path('withdraw/verify/<int:verification_id>/', views.verify_withdrawal, name='verify_withdrawal'),
    path('withdraw/resend/<int:verification_id>/', views.resend_withdrawal_code, name='resend_code'),
    path('withdrawal/receipt/<int:withdrawal_id>/', views.download_withdrawal_pdf, name='download_withdrawal_pdf'),    
    path('support/ticket/<str:ticket_id>/', views.ticket_detail, name='ticket_detail'),
    # Auth System
    path('accounts/register/', views.register_view, name='register'),
    path('accounts/login/', views.login_view, name='login'),
    path('accounts/logout/', views.logoutView, name='logout'),
    path('accounts/settings/', views.settings_view, name='settings'),
    path('unified_deposit/', views.unified_deposit, name='unified_deposit'),    
    # Financials
    path('transactions/', views.transaction_history, name='transaction_history'),   

    # Admin / Staff
    path('staff/overview/', views.admin_overview, name='admin_overview'),
]