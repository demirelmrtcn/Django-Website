from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Transaction(models.Model):
    # Seçenekler: Gelir mi, Gider mi?
    TRANSACTION_TYPES = (
        ('expense', 'Harcama'),
        ('income', 'Gelen Para'),
    )
    
    # Kategori seçenekleri
    CATEGORY_CHOICES = (
        ('general', 'Genel'),
        ('food', 'Yemek & Restoran'),
        ('transport', 'Ulaşım'),
        ('market', 'Market & Alışveriş'),
        ('bills', 'Fatura & Abonelik'),
        ('entertainment', 'Eğlence'),
        ('clothing', 'Giyim'),
        ('health', 'Sağlık'),
        ('education', 'Eğitim'),
        ('rent', 'Kira'),
        ('salary', 'Maaş'),
        ('bonus', 'Prim & Bonus'),
        ('other', 'Diğer'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)  # Hangi kullanıcının işlemi?
    title = models.CharField(max_length=100, verbose_name="Açıklama / Ad")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tutar (TL)")
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES, default='expense')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general', verbose_name="Kategori")
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
    
    # --- STOK DURUMU ---
    is_in_stock = models.BooleanField(default=True, verbose_name="Stokta Var")

    def __str__(self):
        return self.product_name

# --- YENİ MODEL: FİYAT GEÇMİŞİ (GRAFİK İÇİN) ---
class PriceHistory(models.Model):
    product = models.ForeignKey(TrackedProduct, on_delete=models.CASCADE, related_name='history')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.product.product_name} - {self.price} ({self.date})"
    
    class Meta:
        indexes = [
            models.Index(fields=['product', '-date']),  # Optimize price history queries
        ]
        ordering = ['-date']


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


# Note and CalendarEvent models removed - unused features


# ============================================================
# DECISION MAKER MODELS
# ============================================================

class DecisionWheel(models.Model):
    """Kullanıcının kaydettiği karar çarkları"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, verbose_name="Çark Adı")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_template = models.BooleanField(default=False, verbose_name="Şablon mu?")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Karar Çarkı"
        verbose_name_plural = "Karar Çarkları"


class WheelOption(models.Model):
    """Çarktaki seçenekler"""
    wheel = models.ForeignKey(DecisionWheel, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=100, verbose_name="Seçenek")
    color = models.CharField(max_length=20, default="#667eea", verbose_name="Renk")
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.wheel.name} - {self.text}"

    class Meta:
        ordering = ['order']
        verbose_name = "Çark Seçeneği"
        verbose_name_plural = "Çark Seçenekleri"


class DecisionHistory(models.Model):
    """Karar geçmişi"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    wheel_name = models.CharField(max_length=100, verbose_name="Çark Adı")
    result = models.CharField(max_length=100, verbose_name="Sonuç")
    decided_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.wheel_name} → {self.result}"

    class Meta:
        ordering = ['-decided_at']
        verbose_name = "Karar Geçmişi"
        verbose_name_plural = "Karar Geçmişleri"


# ============================================================
# WATCH TRACKER MODELS (Movies, Series, Books)
# ============================================================

class WatchItem(models.Model):
    """Movies, TV Series, Books, Podcasts tracking"""
    ITEM_TYPES = [
        ('movie', 'Film'),
        ('series', 'Dizi'),
        ('book', 'Kitap'),
        ('podcast', 'Podcast'),
        ('documentary', 'Belgesel'),
    ]
    
    STATUS_CHOICES = [
        ('planning', 'İzleyeceğim/Okuyacağım'),
        ('ongoing', 'İzliyorum/Okuyorum'),
        ('completed', 'Tamamlandı'),
        ('dropped', 'Bıraktım'),
        ('paused', 'Duraklattım'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, verbose_name="Başlık")
    item_type = models.CharField(max_length=20, choices=ITEM_TYPES, verbose_name="Tür")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning', verbose_name="Durum")
    
    # Metadata
    genre = models.CharField(max_length=100, blank=True, verbose_name="Kategori")  # Dram, Komedi, Bilim Kurgu
    creator = models.CharField(max_length=200, blank=True, verbose_name="Yönetmen/Yazar")
    year = models.IntegerField(null=True, blank=True, verbose_name="Yıl")
    poster_url = models.URLField(max_length=500, blank=True, verbose_name="Poster URL")
    
    # TMDB Integration (auto-fetched)
    tmdb_id = models.IntegerField(null=True, blank=True, verbose_name="TMDB ID")
    backdrop_url = models.URLField(max_length=500, blank=True, verbose_name="Backdrop URL")  # For hero section
    overview = models.TextField(blank=True, verbose_name="Açıklama")  # Synopsis from TMDB
    
    # Progress tracking
    total_episodes = models.IntegerField(null=True, blank=True, verbose_name="Toplam Bölüm")  # For series
    current_episode = models.IntegerField(default=0, verbose_name="Güncel Bölüm")
    total_pages = models.IntegerField(null=True, blank=True, verbose_name="Toplam Sayfa")  # For books
    current_page = models.IntegerField(default=0, verbose_name="Güncel Sayfa")
    
    # Personal data
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, verbose_name="Puan")  # 0.0-10.0
    review = models.TextField(blank=True, verbose_name="İnceleme")
    favorite_quotes = models.TextField(blank=True, verbose_name="Favori Alıntılar")  # Multiple quotes separated
    
    # Sharing
    is_shared = models.BooleanField(default=False, verbose_name="Ortak İzleniyor")  # Couple watching together
    
    # Dates
    started_at = models.DateField(null=True, blank=True, verbose_name="Başlangıç Tarihi")
    completed_at = models.DateField(null=True, blank=True, verbose_name="Bitiş Tarihi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def progress_percentage(self):
        """Calculate completion percentage"""
        if self.item_type in ['series', 'podcast', 'documentary']:
            if self.total_episodes and self.total_episodes > 0:
                return round((self.current_episode / self.total_episodes) * 100, 1)
        elif self.item_type == 'book':
            if self.total_pages and self.total_pages > 0:
                return round((self.current_page / self.total_pages) * 100, 1)
        return 0.0
    
    @property
    def is_completed(self):
        """Check if item is completed"""
        return self.status == 'completed'
    
    def __str__(self):
        return f"{self.title} ({self.get_item_type_display()})"
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "İzlenen/Okunan"
        verbose_name_plural = "İzlenenler/Okunanlar"


# ============================================================
# RESTAURANT/PLACE ARCHIVE MODELS
# ============================================================

class Place(models.Model):
    """Restaurants, cafes, venues visited"""
    CATEGORY_CHOICES = [
        ('restaurant', 'Restoran'),
        ('cafe', 'Kafe'),
        ('bar', 'Bar/Pub'),
        ('fastfood', 'Fast Food'),
        ('bakery', 'Fırın/Pastane'),
        ('dessert', 'Tatlı/Dondurma'),
        ('other', 'Diğer'),
    ]
    
    PRICE_RANGE = [
        (1, '₺ (Ekonomik)'),
        (2, '₺₺ (Orta)'),
        (3, '₺₺₺ (Pahalı)'),
        (4, '₺₺₺₺ (Lüks)'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, verbose_name="Mekan Adı")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name="Kategori")
    cuisine_type = models.CharField(max_length=100, blank=True, verbose_name="Mutfak Türü")  # İtalyan, Japon, Türk
    
    # Location
    address = models.TextField(blank=True, verbose_name="Adres")
    city = models.CharField(max_length=100, default='İstanbul', verbose_name="Şehir")
    district = models.CharField(max_length=100, blank=True, verbose_name="İlçe")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="Enlem")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="Boylam")
    
    # Details
    price_range = models.IntegerField(choices=PRICE_RANGE, default=2, verbose_name="Fiyat Aralığı")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    website = models.URLField(max_length=300, blank=True, verbose_name="Website")
    
    # Internal metadata (auto-calculated)
    times_visited = models.IntegerField(default=0, verbose_name="Ziyaret Sayısı")
    average_rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0, verbose_name="Ortalama Puan")
    average_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name="Ortalama Harcama")
    
    # External data (Google Places API)
    google_place_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Google Place ID")
    
    # Unsplash Integration (auto-fetched photos)
    photo_url = models.URLField(max_length=500, blank=True, verbose_name="Fotoğraf URL")  # Main photo from Unsplash
    photo_photographer = models.CharField(max_length=200, blank=True, verbose_name="Fotoğrafçı")  # Credit attribution
    unsplash_id = models.CharField(max_length=100, blank=True, verbose_name="Unsplash ID")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def update_statistics(self):
        """Recalculate times visited, average rating, average cost"""
        from django.db.models import Avg, Count
        visits = self.visits.all()
        self.times_visited = visits.count()
        if visits.exists():
            self.average_rating = visits.aggregate(Avg('rating'))['rating__avg'] or 0
            self.average_cost = visits.aggregate(Avg('cost'))['cost__avg'] or 0
        self.save()
    
    def __str__(self):
        return f"{self.name} ({self.city})"
    
    class Meta:
        ordering = ['-average_rating', '-times_visited']
        verbose_name = "Mekan"
        verbose_name_plural = "Mekanlar"


class PlaceVisit(models.Model):
    """Individual visit to a place"""
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='visits', verbose_name="Mekan")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Kullanıcı")
    
    visit_date = models.DateField(default=timezone.now, verbose_name="Ziyaret Tarihi")
    rating = models.DecimalField(max_digits=3, decimal_places=1, verbose_name="Puan")  # 0.0-5.0
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name="Harcama (₺)")
    
    notes = models.TextField(blank=True, verbose_name="Notlar")
    what_we_ate = models.TextField(blank=True, verbose_name="Ne Yedik")  # Meal descriptions
    
    # Photos
    photo1 = models.ImageField(upload_to='place_photos/', null=True, blank=True, verbose_name="Fotoğraf 1")
    photo2 = models.ImageField(upload_to='place_photos/', null=True, blank=True, verbose_name="Fotoğraf 2")
    photo3 = models.ImageField(upload_to='place_photos/', null=True, blank=True, verbose_name="Fotoğraf 3")
    
    would_return = models.BooleanField(default=True, verbose_name="Tekrar Gider miyiz?")
    is_favorite = models.BooleanField(default=False, verbose_name="Favori")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        """Override save to update place statistics"""
        super().save(*args, **kwargs)
        self.place.update_statistics()
    
    def __str__(self):
        return f"{self.place.name} - {self.visit_date}"
    
    class Meta:
        ordering = ['-visit_date']
        verbose_name = "Mekan Ziyareti"
        verbose_name_plural = "Mekan Ziyaretleri"


class PlaceRecommendation(models.Model):
    """Cached recommendations for performance"""
    source_place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='recommendations', verbose_name="Kaynak Mekan")
    recommended_place_data = models.TextField(verbose_name="Öneri Verisi")  # Store JSON as string (SQLite compatible)
    similarity_score = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Benzerlik Skoru")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def set_data(self, data_dict):
        """Store dictionary as JSON string"""
        import json
        self.recommended_place_data = json.dumps(data_dict, ensure_ascii=False)
    
    def get_data(self):
        """Retrieve JSON string as dictionary"""
        import json
        if self.recommended_place_data:
            return json.loads(self.recommended_place_data)
        return {}
    
    def __str__(self):
        return f"{self.source_place.name} için öneri"
    
    class Meta:
        ordering = ['-similarity_score']
        verbose_name = "Mekan Önerisi"
        verbose_name_plural = "Mekan Önerileri"
