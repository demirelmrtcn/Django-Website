from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Transaction(models.Model):
    # Seçenekler: Gelir mi, Gider mi?
    TRANSACTION_TYPES = (
        ('expense', 'Harcama'),
        ('income', 'Gelen Para'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)  # Hangi kullanıcının işlemi?
    title = models.CharField(max_length=100, verbose_name="Açıklama / Ad")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tutar (TL)")
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES, default='expense')
    date = models.DateField(default=timezone.now, verbose_name="Tarih")
    installment_count = models.IntegerField(default=0, verbose_name="Taksit Sayısı (Peşinse 0)")
    is_recurring = models.BooleanField(default=False, verbose_name="Her Ay Tekrarla")
    created_at = models.DateTimeField(auto_now_add=True)  # Kayıt oluşturulma zamanı

    def __str__(self):
        return f"{self.title} - {self.amount} TL"

    class Meta:
        ordering = ['-date']  # En yeni tarih en üstte görünsün


class TrackedProduct(models.Model):
    STATUS_CHOICES = (
        ('stable', 'Aynı Fiyat'),
        ('dropped', 'Fiyat Düştü'),
        ('increased', 'Fiyat Yükseldi'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    url = models.URLField(max_length=500, verbose_name="Ürün Linki")
    product_name = models.CharField(max_length=255, verbose_name="Ürün Adı")
    site_name = models.CharField(max_length=50, verbose_name="Site")

    # Fiyat Alanları
    current_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Güncel Fiyat")
    previous_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Önceki Fiyat",
                                         default=0.0)  # <--- YENİ
    original_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Orijinal Fiyat", default=0.0)

    seller_name = models.CharField(max_length=100, verbose_name="Satıcı", blank=True, null=True)
    last_checked = models.DateTimeField(auto_now=True, verbose_name="Son Kontrol")
    custom_name = models.CharField(max_length=255, verbose_name="Sizin Verdiğiniz İsim", blank=True, null=True)

    # --- YENİ EKLENEN ALANLAR ---
    notification_email = models.EmailField(verbose_name="Bildirim Maili", default="")
    last_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='stable', verbose_name="Son Durum")
    
    # --- VARYANT ALANLARI (SEPHORA İÇİN) ---
    variant_sku = models.CharField(max_length=100, blank=True, null=True, verbose_name="Varyant SKU")
    variant_size = models.CharField(max_length=50, blank=True, null=True, verbose_name="Boyut/Varyant")
    
    # --- TRENDYOL PLUS FİYATI ---
    plus_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Plus Fiyatı")

    def __str__(self):
        return self.product_name

# --- YENİ MODEL: FİYAT GEÇMİŞİ (GRAFİK İÇİN) ---
class PriceHistory(models.Model):
    product = models.ForeignKey(TrackedProduct, on_delete=models.CASCADE, related_name='history')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.product.product_name} - {self.price} ({self.date})"


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
