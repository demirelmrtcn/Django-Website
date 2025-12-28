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

    # --- ORGANIZER REMOVED ---
    # Organizer feature has been removed. URLs preserved as comments for future reference.
    # path('organizer/', views.organizer_dashboard, name='organizer_dashboard'),
    # path('organizer/note/create/', views.create_note, name='create_note'),
    # path('organizer/note/<int:id>/update/', views.update_note, name='update_note'),
    # path('organizer/note/<int:id>/', views.get_note, name='get_note'),
    # path('organizer/note/<int:id>/delete/', views.delete_note, name='delete_note'),
    # path('organizer/event/create/', views.create_event, name='create_event'),
    # path('organizer/event/<int:id>/delete/', views.delete_event, name='delete_event'),
    # path('organizer/events/', views.get_events, name='get_events'),

    # --- MEDIA DOWNLOADER ---
    path('medya-indir/', views.media_downloader_dashboard, name='media_downloader'),
    path('medya-indir/download/', views.download_media, name='download_media'),
]
