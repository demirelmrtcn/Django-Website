from django import forms
from .models import Transaction, TrackedProduct # Modelimizi çağırıyoruz

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        # Kullanıcıdan isteyeceğimiz alanlar:
        fields = ['date', 'title', 'amount', 'category', 'installment_count', 'is_recurring']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Maaş, Kira'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'installment_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            # Checkbox için stil
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class AddProductForm(forms.ModelForm):
    class Meta:
        model = TrackedProduct
        # notification_email alanını ekledik
        fields = ['url', 'custom_name', 'notification_email']
        widgets = {
            'url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'custom_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Oyuncu Koltuğu'}),
            'notification_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ornek@email.com'}),
        }
