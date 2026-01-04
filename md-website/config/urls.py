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
    path('fiyat-takip/stoksuz-temizle/', views.delete_out_of_stock, name='delete_out_of_stock'),

    # --- MEDIA DOWNLOADER ---
    path('medya-indir/', views.media_downloader_dashboard, name='media_downloader'),
    path('medya-indir/download/', views.download_media, name='download_media'),

    # --- DECISION MAKER ---
    path('karar-verici/', views.decision_maker_dashboard, name='decision_maker'),
    path('karar-verici/kaydet/', views.save_wheel, name='save_wheel'),
    path('karar-verici/cark/<int:id>/', views.get_wheel, name='get_wheel'),
    path('karar-verici/sil/<int:id>/', views.delete_wheel, name='delete_wheel'),
    path('karar-verici/gecmis-kaydet/', views.save_decision_history, name='save_decision_history'),
    
    # --- WATCH TRACKER ---
    path('izlediklerim/', views.watch_tracker_dashboard, name='watch_tracker'),
    path('izlediklerim/yeni/', views.add_watch_item_page, name='add_watch_item_page'),  # Dedicated add page
    path('izlediklerim/ara/', views.search_tmdb_ajax, name='search_tmdb'),  # TMDB search AJAX
    path('izlediklerim/ekle/', views.add_watch_item, name='add_watch_item'),  # Old AJAX endpoint (keep for compatibility)
    path('izlediklerim/<int:id>/', views.watch_item_detail, name='watch_item_detail'),
    # API Endpoints for Modal
    path('api/watch-item/<int:id>/', views.get_watch_item_json, name='get_watch_item_json'),
    path('api/watch-item/<int:id>/update/', views.update_watch_item_json, name='update_watch_item_json'),
    path('api/watch-item/<int:id>/delete/', views.delete_watch_item_json, name='delete_watch_item_json'),
    path('izlediklerim/<int:id>/guncelle/', views.update_watch_progress, name='update_watch_progress'),
    path('izlediklerim/<int:id>/sil/', views.delete_watch_item, name='delete_watch_item'),
    
    # --- PLACE ARCHIVE ---
    path('mekanlar/', views.place_archive_dashboard, name='place_archive'),
    path('mekanlar/yeni/', views.add_place_visit_page, name='add_place_visit_page'),  # Dedicated add page
    path('mekanlar/fetch-photos/', views.fetch_place_photos_ajax, name='fetch_place_photos'),  # Unsplash photos AJAX
    path('mekanlar/ekle/', views.add_place_visit, name='add_place_visit'),  # Old form endpoint (keep for compatibility)
    path('mekanlar/<int:id>/', views.place_detail, name='place_detail'),
    path('mekanlar/<int:id>/oneriler/', views.get_place_recommendations, name='place_recommendations'),
    path('mekanlar/<int:id>/sil/', views.delete_place, name='delete_place'),
]
