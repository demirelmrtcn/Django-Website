from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
import logging

logger = logging.getLogger(__name__)
scheduler = None

def start():
    """Start the background scheduler for automatic price checking"""
    global scheduler
    
    # Sadece bir kere başlat (Django'nun reload mekanizması için)
    if scheduler is not None:
        return
    
    scheduler = BackgroundScheduler()
    
    # Her 30 dakikada bir fiyat kontrolü yap
    scheduler.add_job(
        run_price_check,
        'interval',
        minutes=30,
        id='price_check_job',
        replace_existing=True,
        max_instances=1  # Aynı anda sadece bir instance çalışsın
    )
    
    scheduler.start()
    logger.info("🤖 Otomatik fiyat takip sistemi başlatıldı! (Her 30 dakikada bir çalışacak)")
    print("🤖 Otomatik fiyat takip sistemi başlatıldı! (Her 30 dakikada bir çalışacak)")
    
    # İlk kontrolü hemen yap (30 dakika bekleme)
    logger.info("🚀 İlk fiyat kontrolü başlatılıyor...")
    print("🚀 İlk fiyat kontrolü başlatılıyor...")
    run_price_check()

def run_price_check():
    """Background job that checks all product prices"""
    from .price_checker import check_all_prices
    
    logger.info("⏰ Otomatik fiyat kontrolü başlıyor...")
    print("⏰ Otomatik fiyat kontrolü başlıyor...")
    
    try:
        check_all_prices()
        logger.info("✅ Otomatik fiyat kontrolü tamamlandı!")
        print("✅ Otomatik fiyat kontrolü tamamlandı!")
    except Exception as e:
        logger.error(f"❌ Otomatik fiyat kontrolü hatası: {e}")
        print(f"❌ Otomatik fiyat kontrolü hatası: {e}")

def shutdown():
    """Shutdown the scheduler gracefully"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler kapatıldı")
