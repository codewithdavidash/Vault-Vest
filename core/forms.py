from django import forms
from django.contrib.auth.models import User
from .models import *

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl focus:ring-4 ring-indigo-500/5 focus:border-indigo-500 outline-none transition-all font-bold',
        'placeholder': '••••••••'
    }))

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl focus:ring-4 ring-indigo-500/5 focus:border-indigo-500 outline-none transition-all font-bold',
                'placeholder': 'Username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl focus:ring-4 ring-indigo-500/5 focus:border-indigo-500 outline-none transition-all font-bold',
                'placeholder': 'name@company.com'
            }),
        }

    # CRITICAL: This hashes the password so it's secure
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class DepositForm(forms.ModelForm):
    class Meta:
        model = Transaction  # Updated to your Transaction model
        fields = [
            'amount', 'gateway', 'crypto_currency', 
            'card_type', 'card_code', 'receipt'
        ]
        widgets = {
            # Amount Input
            'amount': forms.NumberInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-5 pl-10 rounded-2xl focus:bg-white focus:border-indigo-500 outline-none transition-all font-bold text-slate-900',
                'placeholder': '0.00'
            }),
            
            # Gateway Selector (Crypto vs Giftcard)
            'gateway': forms.Select(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-5 rounded-2xl focus:bg-white focus:border-indigo-500 outline-none appearance-none font-bold text-slate-700 cursor-pointer',
                'id': 'gateway-selector'
            }),

            # Crypto Specific
            'crypto_currency': forms.Select(choices=[('BTC', 'Bitcoin'), ('USDT', 'Tether (TRC20)'), ('ETH', 'Ethereum')], attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-5 rounded-2xl focus:bg-white focus:border-indigo-500 outline-none font-bold text-slate-700',
            }),

            # Giftcard Specific
            'card_type': forms.Select(choices=[('AMAZON', 'Amazon'), ('APPLE', 'Apple/iTunes'), ('STEAM', 'Steam')], attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-5 rounded-2xl focus:bg-white focus:border-indigo-500 outline-none font-bold text-slate-700',
            }),
            'card_code': forms.TextInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-5 rounded-2xl focus:bg-white focus:border-indigo-500 outline-none font-mono font-bold text-slate-900',
                'placeholder': 'Enter card claim code'
            }),

            # Receipt/Proof Upload
            'receipt': forms.FileInput(attrs={
                'class': 'hidden',
                'id': 'proof-upload',
                'onchange': 'updateFileName(this)'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure only relevant choices are shown
        self.fields['gateway'].choices = [
            ('CRYPTO', 'Cryptocurrency'),
            ('GIFTCARD', 'Gift Card')
        ]
        
class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl focus:ring-4 ring-indigo-500/5 focus:border-indigo-500 outline-none transition-all font-bold',
        'placeholder': 'Username'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl focus:ring-4 ring-indigo-500/5 focus:border-indigo-500 outline-none transition-all font-bold',
        'placeholder': '••••••••'
    }))

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = InvestmentProfile
        # Expanded to include your new model fields
        fields = ['phone_number', 'ssn_number', 'id_type', 'settlement_address']
        
        widgets = {
            'phone_number': forms.TextInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl focus:ring-4 ring-indigo-500/5 outline-none transition-all',
                'placeholder': '+1 (555) 000-0000'
            }),
            'ssn_number': forms.TextInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl focus:ring-4 ring-indigo-500/5 outline-none transition-all',
                'placeholder': 'Tax ID or SSN'
            }),
            'id_type': forms.Select(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl focus:ring-4 ring-indigo-500/5 outline-none transition-all'
            }),
            'settlement_address': forms.TextInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 p-4 rounded-2xl font-mono text-sm focus:ring-4 ring-indigo-500/5 outline-none transition-all',
                'placeholder': 'Your BTC or USDT Address'
            }),
        }