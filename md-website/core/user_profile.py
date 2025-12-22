from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    """User profile for email verification and additional user data"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    email_verified = models.BooleanField(default=False, verbose_name="Email Doğrulandı")
    verification_code = models.CharField(max_length=6, blank=True, null=True, verbose_name="Doğrulama Kodu")
    verification_code_created = models.DateTimeField(null=True, blank=True, verbose_name="Kod Oluşturma Zamanı")
    
    def generate_verification_code(self):
        """Generate a 6-digit verification code"""
        import random
        self.verification_code = str(random.randint(100000, 999999))
        self.verification_code_created = timezone.now()
        self.save()
        return self.verification_code
    
    def is_code_valid(self, code):
        """Check if verification code is valid (15 minutes expiry)"""
        if not self.verification_code or not self.verification_code_created:
            return False
        
        # Kod 15 dakika (900 saniye) geçerli
        time_diff = (timezone.now() - self.verification_code_created).total_seconds()
        if time_diff > 900:
            return False
        
        return self.verification_code == code
    
    def __str__(self):
        return f"{self.user.username} - {'Verified' if self.email_verified else 'Not Verified'}"
    
    class Meta:
        verbose_name = "Kullanıcı Profili"
        verbose_name_plural = "Kullanıcı Profilleri"
