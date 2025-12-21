from django import template
from django.utils import timezone
from dateutil.relativedelta import relativedelta  # Tarih hesaplamaları için
import datetime

register = template.Library()


@register.filter
def smart_status(transaction):
    """
    İşlemin durumuna göre akıllı metin ve renk sınıfı döndürür.
    Dönen değer: (Metin, CSS Class)
    """
    today = timezone.now().date()
    trans_date = transaction.date

    # 1. DURUM: TAKSİTLİ İŞLEM
    if transaction.installment_count > 1:
        # Taksit bitiş tarihini bul (Başlangıç + Taksit Sayısı kadar ay)
        end_date = trans_date + relativedelta(months=transaction.installment_count)

        # Eğer taksitler bittiyse
        if today > end_date:
            return "Taksit Bitti", "success"

        # Taksit devam ediyorsa, bugünden sonraki ilk ödeme tarihini bul
        # Ödeme günü her ayın 'trans_date.day'i olacak.
        next_payment = trans_date
        while next_payment < today:
            next_payment += relativedelta(months=1)

        days_left = (next_payment - today).days

        if days_left == 0:
            return "Taksit Bugün", "warning text-dark"

        # Kaçıncı taksitte olduğumuzu bulalım
        current_installment = ((today.year - trans_date.year) * 12 + (today.month - trans_date.month)) + 1
        if current_installment < 1: current_installment = 1

        return f"{days_left} Gün Kaldı ({current_installment}/{transaction.installment_count})", "info text-dark"

    # 2. DURUM: TEKRARLAYAN İŞLEM (MAAŞ / KİRA)
    elif transaction.is_recurring:
        # İşlem tarihi geçmişte kaldıysa, bir sonraki ayın aynı gününü hedefle
        next_occurrence = trans_date
        while next_occurrence < today:
            next_occurrence += relativedelta(months=1)

        days_left = (next_occurrence - today).days

        if days_left == 0:
            return "Ödeme Bugün!", "warning text-dark"
        else:
            return f"Sonraki: {days_left} Gün", "primary"

    # 3. DURUM: TEK SEFERLİK İŞLEM (Eski Mantık)
    else:
        delta = trans_date - today
        if delta.days == 0:
            return "Bugün", "warning text-dark"
        elif delta.days > 0:
            return f"{delta.days} Gün Kaldı", "secondary"
        else:
            return "Tamamlandı", "success"


# HTML tarafında (Text, Class) ikilisini ayırmak için yardımcı filtreler
@register.filter
def get_status_text(transaction):
    return smart_status(transaction)[0]


@register.filter
def get_status_class(transaction):
    return smart_status(transaction)[1]