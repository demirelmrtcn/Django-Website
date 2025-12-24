"""
Registration and Email Verification Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.mail import send_mail, EmailMultiAlternatives
from .models import UserProfile
from .forms import RegisterForm, VerificationForm
import requests
from django.conf import settings


def register(request):
    """User registration with email and CAPTCHA validation"""
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        
        # reCAPTCHA v2 validation
        recaptcha_response = request.POST.get('g-recaptcha-response')
        data = {
            'secret': settings.RECAPTCHA_SECRET_KEY,
            'response': recaptcha_response
        }
        r = requests.post('https://www.google.com/recaptcha/api/siteverify', data=data)
        result = r.json()
        
        if not result.get('success'):
            messages.error(request, "reCAPTCHA doğrulaması başarısız. Lütfen tekrar deneyin.")
            return render(request, 'core/register.html', {'form': form})
        
        if form.is_valid():
            # Kullanıcı oluştur ama aktif etme (email doğrulanana kadar)
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            
            # UserProfile oluştur ve doğrulama kodu gönder
            profile, created = UserProfile.objects.get_or_create(user=user)
            code = profile.generate_verification_code()
            
            # Email gönder
            send_verification_email(user.email, code, user.username)
            
            messages.success(request, f"Kayıt başarılı! {user.email} adresine doğrulama kodu gönderildi.")
            return redirect('verify_email', user_id=user.id)
    else:
        form = RegisterForm()
    
    return render(request, 'core/register.html', {
        'form': form,
        'recaptcha_site_key': settings.RECAPTCHA_SITE_KEY
    })


def verify_email(request, user_id):
    """Email verification with 6-digit code"""
    user = get_object_or_404(User, id=user_id)
    
    # Eğer zaten doğrulanmışsa login'e yönlendir
    if user.is_active:
        messages.info(request, "Email zaten doğrulanmış. Giriş yapabilirsiniz.")
        return redirect('login')
    
    if request.method == 'POST':
        form = VerificationForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            
            if user.profile.is_code_valid(code):
                # Email doğrulandı, kullanıcıyı aktif et
                user.is_active = True
                user.save()
                
                user.profile.email_verified = True
                user.profile.verification_code = None
                user.profile.save()
                
                # Kullanıcıyı otomatik olarak giriş yap
                from django.contrib.auth import login
                login(request, user)
                
                messages.success(request, "✅ Email doğrulandı! Hoş geldiniz!")
                return redirect('dashboard')  # Dashboard'a yönlendir
            else:
                messages.error(request, "❌ Geçersiz veya süresi dolmuş kod! (Kod 15 dakika geçerlidir)")
    else:
        form = VerificationForm()
    
    return render(request, 'core/verify_email.html', {
        'form': form,
        'user': user,
        'email': user.email
    })


def resend_verification_code(request, user_id):
    """Resend verification code"""
    user = get_object_or_404(User, id=user_id)
    
    if user.is_active:
        messages.info(request, "Email zaten doğrulanmış.")
        return redirect('login')
    
    # Yeni kod oluştur ve gönder
    code = user.profile.generate_verification_code()
    send_verification_email(user.email, code, user.username)
    
    messages.success(request, f"Yeni doğrulama kodu {user.email} adresine gönderildi.")
    return redirect('verify_email', user_id=user.id)


def send_verification_email(email, code, username):
    """Send verification code email"""
    subject = "🔐 Email Doğrulama Kodu"
    
    # Plain text message
    message = f"""
    Merhaba {username},
    
    Kayıt işleminizi tamamlamak için doğrulama kodunuz:
    
    {code}
    
    Bu kod 15 dakika geçerlidir.
    
    İyi günler!
    """
    
    # HTML message
    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #333; text-align: center;">Hoş Geldiniz! 🎉</h2>
            <p style="color: #666; font-size: 16px;">Merhaba <strong>{username}</strong>,</p>
            <p style="color: #666; font-size: 16px;">Kayıt işleminizi tamamlamak için aşağıdaki doğrulama kodunu kullanın:</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; text-align: center; margin: 30px 0;">
                <h1 style="color: #007bff; font-size: 48px; margin: 0; letter-spacing: 10px; font-family: 'Courier New', monospace;">{code}</h1>
            </div>
            
            <p style="color: #999; font-size: 14px; text-align: center;">⏰ Bu kod 15 dakika geçerlidir.</p>
            
            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
            
            <p style="color: #999; font-size:12px; text-align: center;">Bu e-postayı siz talep etmediyseniz lütfen dikkate almayın.</p>
        </div>
    </body>
    </html>
    """
    
    try:
        msg = EmailMultiAlternatives(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
        msg.attach_alternative(html_message, "text/html")
        msg.send()
        print(f"✉️ Doğrulama kodu gönderildi: {email}")
    except Exception as e:
        print(f"❌ Email gönderme hatası: {e}")
