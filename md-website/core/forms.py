from django import forms
from .models import Transaction, TrackedProduct # Modelimizi çağırıyoruz
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        # Kullanıcıdan isteyeceğimiz alanlar:
        fields = ['date', 'title', 'amount', 'installment_count', 'is_recurring']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Maaş, Kira'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
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


class RegisterForm(UserCreationForm):
    """Registration form with email and CAPTCHA"""
    email = forms.EmailField(
        required=True,
        label="E-posta",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ornek@email.com'})
    )
    
    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'kullaniciadi'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': '********'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': '********'})
        self.fields['username'].label = "Kullanıcı Adı"
        self.fields['password1'].label = "Şifre"
        self.fields['password2'].label = "Şifre Onay"
    
    def clean_email(self):
        """Check if email is already registered (case-insensitive)"""
        email = self.cleaned_data.get('email')
        if email:
            # Case-insensitive email kontrolü
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError("Bu e-posta adresi zaten kayıtlı!")
        return email


class VerificationForm(forms.Form):
    """Email verification code form"""
    code = forms.CharField(
        max_length=6,
        min_length=6,
        label="Doğrulama Kodu",
        widget=forms.TextInput(attrs={'class': 'form-control text-center', 'placeholder': '000000', 'style': 'font-size: 24px; letter-spacing: 10px;'}),
        help_text="E-postanıza gönderilen 6 haneli kodu girin"
    )
    
    def clean_code(self):
        """Validate code format"""
        code = self.cleaned_data.get('code')
        if not code.isdigit():
            raise ValidationError("Kod sadece rakamlardan oluşmalıdır!")
        return code