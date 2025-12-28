from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views # Django'nun hazır giriş/çıkış sistemi
from core import views # Bizim yazdığımız views dosyası
# Registration disabled - users can only be created via admin panel
# Registration URLs removed: register, verify_email, resend_verification_code

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Ana sayfa ('') olduğunda dashboard açılsın
    path('', views.dashboard, name='dashboard'),
    
    # Login sayfası (Kendi template'imizi kullan diyoruz)
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    
    # Logout sayfası
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('finans/', views.finance_dashboard, name='finance_dashboard'),

    path('sil/<int:id>/', views.delete_transaction, name='delete_transaction'),

    path('fiyat-takip/', views.price_tracking_dashboard, name='price_tracking_dashboard'),

    path('fiyat-takip/sil/<int:id>/', views.delete_product, name='delete_product'),

    path('fiyat-takip/bot-baslat/', views.run_price_bot, name='run_price_bot'),

    # --- MEDIA DOWNLOADER ---
    path('medya-indir/', views.media_downloader_dashboard, name='media_downloader'),
    path('medya-indir/download/', views.download_media, name='download_media'),

    # --- DECISION MAKER ---
    path('karar-verici/', views.decision_maker_dashboard, name='decision_maker'),
    path('karar-verici/kaydet/', views.save_wheel, name='save_wheel'),
    path('karar-verici/cark/<int:id>/', views.get_wheel, name='get_wheel'),
    path('karar-verici/sil/<int:id>/', views.delete_wheel, name='delete_wheel'),
    path('karar-verici/gecmis-kaydet/', views.save_decision_history, name='save_decision_history'),
]
