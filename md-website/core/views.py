from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Avg, Count
from django.utils import timezone
from django.http import StreamingHttpResponse, FileResponse, JsonResponse
from django.db import transaction, models
from .models import (Transaction, TrackedProduct, PriceHistory, Note, CalendarEvent, 
                     DecisionWheel, WheelOption, DecisionHistory, WatchItem, 
                     Place, PlaceVisit, PlaceRecommendation)
from .forms import TransactionForm, AddProductForm
from .utils import get_product_details
import datetime
from dateutil.relativedelta import relativedelta
from django.urls import reverse
from django.core.mail import send_mail, get_connection, EmailMultiAlternatives
from django.conf import settings
from decimal import Decimal
import json
import yt_dlp
import os
import uuid
import tempfile
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
import json
import re

@login_required
def dashboard(request):
    return render(request, 'core/dashboard.html')


@login_required
def finance_dashboard(request):
    # --- 1. YENİ KAYIT İŞLEMİ (POST) ---
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.transaction_type = request.POST.get('type_input', 'expense')
            transaction.save()

            # --- YENİ EKLENEN ÖZELLİK ---
            # Kayıt edilen işlemin tarihini al (Örn: 2025-11)
            target_date = transaction.date.strftime('%Y-%m')

            # Kullanıcıyı direkt o ayın sayfasına yönlendir
            return redirect(f"{reverse('finance_dashboard')}?date={target_date}")
    else:
        form = TransactionForm()

    # --- 2. AY SEÇİMİ VE FİLTRELEME ---
    # URL'den tarihi al (Örn: ?date=2025-11), yoksa bugünü al
    selected_date_str = request.GET.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.datetime.strptime(selected_date_str, '%Y-%m').date()
        except ValueError:
            selected_date = timezone.now().date().replace(day=1)
    else:
        selected_date = timezone.now().date().replace(day=1)

    # Önceki ve Sonraki Ay Linkleri için Hesaplama
    prev_month = (selected_date - relativedelta(months=1)).strftime('%Y-%m')
    next_month = (selected_date + relativedelta(months=1)).strftime('%Y-%m')

    # --- 3. DROPDOWN İÇİN AY LİSTESİ HAZIRLAMA ---
    # Kullanıcıya sunulacak tarih aralığı: Geçmiş 24 ay -> Gelecek 12 ay
    month_list = []
    today_for_range = timezone.now().date().replace(day=1)

    start_range = today_for_range - relativedelta(months=24)
    end_range = today_for_range + relativedelta(months=12)

    current_iter = start_range
    while current_iter <= end_range:
        month_list.append(current_iter)
        current_iter += relativedelta(months=1)

    # Listeyi tersten sırala (En yeni tarih en üstte olsun istersen reverse=True yapabilirsin)
    # month_list.sort(reverse=True)

    # --- 4. VERİLERİ ÇEKME ---
    # Sadece seçili ayın verilerini getir
    transactions = Transaction.objects.filter(
        user=request.user,
        date__year=selected_date.year,
        date__month=selected_date.month
    ).order_by('date')

    # Seçili Ayın Toplamları
    total_income = transactions.filter(transaction_type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    total_expense = transactions.filter(transaction_type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    balance = total_income - total_expense

    # --- 5. GRAFİK İÇİN VERİ HAZIRLIĞI (Son 6 Ay) ---
    chart_labels = []
    chart_income = []
    chart_expense = []

    # Bugünden geriye 6 ay giderek analiz yap
    chart_today = timezone.now().date()
    for i in range(5, -1, -1):  # 5 ay önceden bugüne
        target_date = chart_today - relativedelta(months=i)

        # O ayın tüm verilerini çek
        month_trans = Transaction.objects.filter(
            user=request.user,
            date__year=target_date.year,
            date__month=target_date.month
        )

        inc = month_trans.filter(transaction_type='income').aggregate(Sum('amount'))['amount__sum'] or 0
        exp = month_trans.filter(transaction_type='expense').aggregate(Sum('amount'))['amount__sum'] or 0

        chart_labels.append(target_date.strftime('%B'))  # Ay ismi
        chart_income.append(float(inc))
        chart_expense.append(float(exp))

    # --- 6. KATEGORİ BAZLI HARCAMA ANALİZİ (Pie Chart için) ---
    category_data = transactions.filter(transaction_type='expense').values('category').annotate(
        total=Sum('amount')
    ).order_by('-total')
    
    # Kategori isimlerini Türkçe'ye çevir
    category_labels = []
    category_values = []
    category_colors = {
        'general': '#6366f1',
        'food': '#f59e0b',
        'transport': '#3b82f6',
        'market': '#10b981',
        'bills': '#ef4444',
        'entertainment': '#8b5cf6',
        'clothing': '#ec4899',
        'health': '#14b8a6',
        'education': '#6366f1',
        'rent': '#f97316',
        'salary': '#22c55e',
        'bonus': '#84cc16',
        'other': '#94a3b8',
    }
    category_display_names = dict(Transaction.CATEGORY_CHOICES)
    pie_colors = []
    
    for item in category_data:
        cat_key = item['category']
        category_labels.append(category_display_names.get(cat_key, cat_key))
        category_values.append(float(item['total']))
        pie_colors.append(category_colors.get(cat_key, '#94a3b8'))
    
    # En yüksek harcama kategorisi
    top_category = category_labels[0] if category_labels else 'Henüz yok'
    top_category_amount = category_values[0] if category_values else 0
    
    # Günlük ortalama harcama
    import calendar
    days_in_month = calendar.monthrange(selected_date.year, selected_date.month)[1]
    daily_average = float(total_expense) / days_in_month if total_expense > 0 else 0
    
    # Önceki ay karşılaştırması
    prev_month_date = selected_date - relativedelta(months=1)
    prev_month_expense = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        date__year=prev_month_date.year,
        date__month=prev_month_date.month
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    if prev_month_expense > 0:
        expense_change_percent = ((float(total_expense) - float(prev_month_expense)) / float(prev_month_expense)) * 100
    else:
        expense_change_percent = 0

    context = {
        'transactions': transactions,
        'form': form,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        # Navigasyon Verileri
        'selected_date': selected_date,
        'selected_month_str': selected_date.strftime('%Y-%m'),  # String formatı
        'prev_month': prev_month,
        'next_month': next_month,
        'month_list': month_list,
        # Grafik Verileri
        'chart_labels': chart_labels,
        'chart_income': chart_income,
        'chart_expense': chart_expense,
        # Kategori ve Pie Chart Verileri
        'category_labels': category_labels,
        'category_values': category_values,
        'pie_colors': pie_colors,
        # Ek İstatistikler
        'top_category': top_category,
        'top_category_amount': top_category_amount,
        'daily_average': round(daily_average, 2),
        'expense_change_percent': round(expense_change_percent, 1),
    }
    return render(request, 'core/finance.html', context)



@login_required
def delete_transaction(request, id):
    transaction = get_object_or_404(Transaction, id=id, user=request.user)

    # 1. Silmeden önce tarihin yıl ve ayını alıp saklıyoruz (Örn: 2025-10)
    target_date = transaction.date.strftime('%Y-%m')

    # 2. İşlemi siliyoruz
    transaction.delete()

    # 3. Kullanıcıyı sildiği işlemin olduğu aya geri gönderiyoruz
    # reverse ile ana linki alıp, sonuna ?date=... ekliyoruz.
    return redirect(f"{reverse('finance_dashboard')}?date={target_date}")


@login_required
def price_tracking_dashboard(request):
    if request.method == 'POST' and 'add_product' in request.POST:
        form = AddProductForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data['url']
            custom_name = form.cleaned_data['custom_name']
            email = form.cleaned_data['notification_email']  # Formdan maili al

            # DUPLICATE KONTROLÜ - Aynı URL ve aynı email varsa ekleme
            existing_product = TrackedProduct.objects.filter(
                user=request.user,
                url=url,
                notification_email=email
            ).first()
            
            if existing_product:
                messages.warning(request, 
                    f"Bu ürün ({existing_product.product_name}) zaten bu mail adresiyle takip ediliyor!")
                return redirect('price_tracking_dashboard')

            try:
                scraped_data = get_product_details(url)
            except Exception as e:
                scraped_data = None
                print(f"View Hatası: {e}")

            if scraped_data and scraped_data['price'] > 0:
                TrackedProduct.objects.create(
                    user=request.user,
                    url=url,
                    custom_name=custom_name,
                    notification_email=email,  # Maili kaydet
                    product_name=scraped_data['title'],
                    site_name=scraped_data['site'],
                    current_price=scraped_data['price'],
                    original_price=scraped_data.get('original_price', 0),
                    seller_name=scraped_data['seller'],
                    plus_price=scraped_data.get('plus_price', None)  # Trendyol Plus fiyatı
                )
                messages.success(request, "Ürün başarıyla eklendi!")
            else:
                messages.error(request, "Ürün bilgileri çekilemedi.")

            return redirect('price_tracking_dashboard')
        else:
            messages.error(request, "Form geçersiz.")
            return redirect('price_tracking_dashboard')
    else:
        form = AddProductForm()

    products = TrackedProduct.objects.filter(user=request.user).order_by('-last_checked')

    # --- GRAFİK İÇİN VERİ HAZIRLIĞI (TIME SCALE) ---
    # Her ürün için tarihçeyi çekip {x: timestamp, y: price} formatına çevireceğiz
    chart_data = {
        'datasets': []
    }

    # Eğer ürün varsa grafik verisi oluştur
    if products.exists():
        # Grafik renkleri (Daha canlı ve ayırt edilebilir renkler)
        colors = [
            '#f59e0b',  # amber
            '#10b981',  # emerald
            '#3b82f6',  # blue
            '#ef4444',  # red
            '#8b5cf6',  # violet
            '#ec4899',  # pink
            '#14b8a6',  # teal
            '#f97316',  # orange
        ]

        for i, product in enumerate(products):
            # Son 15 fiyat hareketini al
            history = product.history.all().order_by('date')[:15]

            # Her veri noktası {x: timestamp, y: price} formatında
            data_points = []
            for h in history:
                data_points.append({
                    'x': h.date.isoformat(),  # ISO 8601 format: "2024-12-30T14:30:00"
                    'y': float(h.price)
                })

            # Sadece en az 2 veri noktası olan ürünleri ekle
            if len(data_points) >= 2:
                chart_data['datasets'].append({
                    'productId': product.id,  # JS için ürün ID
                    'label': product.custom_name or product.product_name[:20],
                    'data': data_points,
                    'borderColor': colors[i % len(colors)],
                    'backgroundColor': colors[i % len(colors)] + '20',
                })
            # Veri az olsa bile her ürünü ekle (JS tarafında empty state gösterecek)
            else:
                chart_data['datasets'].append({
                    'productId': product.id,
                    'label': product.custom_name or product.product_name[:20],
                    'data': data_points,
                    'borderColor': colors[i % len(colors)],
                })

    # Dropdown için sadece fiyat geçmişi olan ürünleri filtrele
    products_with_history = [p for p in products if p.history.count() >= 2]

    context = {
        'products': products,
        'products_with_history': products_with_history,  # Dropdown için
        'form': form,
        'chart_data': json.dumps(chart_data),
        # İstatistikler
        'total_products': products.count(),
        'dropped_count': products.filter(last_status='dropped').count(),
        'increased_count': products.filter(last_status='increased').count(),
        'unique_emails': products.values('notification_email').distinct().count(),
        'out_of_stock_count': products.filter(is_in_stock=False).count(),
        'last_check_time': products.order_by('-last_checked').first().last_checked if products.exists() else None,
        # Desteklenen siteler
        'supported_sites': [
            {'name': 'Trendyol', 'color': '#f27a1a'},
            {'name': 'Hepsiburada', 'color': '#ff6000'},
            {'name': 'Amazon', 'color': '#ff9900'},
            {'name': 'Zara', 'color': '#000000'},
            {'name': 'Sephora', 'color': '#000000'},
            {'name': 'MAC', 'color': '#000000'},
            {'name': 'Kiko', 'color': '#000000'},
            {'name': 'Gratis', 'color': '#e91e63'},
            {'name': 'Oysho', 'color': '#000000'},
            {'name': 'Mango', 'color': '#000000'},
            {'name': 'Bershka', 'color': '#000000'},
            {'name': 'Yves Rocher', 'color': '#5a8f3e'},
        ],
    }
    return render(request, 'core/price_tracking.html', context)


@login_required
def delete_product(request, id):
    product = get_object_or_404(TrackedProduct, id=id, user=request.user)
    product.delete()
    return redirect('price_tracking_dashboard')


@login_required
def delete_out_of_stock(request):
    """Stokta olmayan tüm ürünleri sil"""
    deleted_count = TrackedProduct.objects.filter(
        user=request.user, 
        is_in_stock=False
    ).delete()[0]
    
    if deleted_count > 0:
        messages.success(request, f"{deleted_count} stokta olmayan ürün silindi.")
    else:
        messages.info(request, "Silinecek stokta olmayan ürün bulunamadı.")
    
    return redirect('price_tracking_dashboard')


@login_required
def run_price_bot(request):
    def event_stream():
        # Veritabanı kilidini önlemek için list() içine alıyoruz
        products = list(TrackedProduct.objects.filter(user=request.user))
        total_products = len(products)

        email_queue = {}
        updated_count = 0

        yield json.dumps({
            'status': 'start',
            'total': total_products,
            'message': 'Bot başlatılıyor...'
        }) + "\n"

        for index, product in enumerate(products, 1):
            yield json.dumps({
                'status': 'progress',
                'current': index,
                'total': total_products,
                'message': f"Taranıyor: {product.product_name} ({product.site_name})",
                'percent': int((index / total_products) * 100)
            }) + "\n"

            try:
                new_data = get_product_details(product.url)
            except:
                new_data = None

            if new_data and new_data['price'] > 0:
                new_price = Decimal(str(new_data['price']))
                old_price = product.current_price

                # ŞU ANKİ ZAMANI ALIYORUZ
                current_now = timezone.now()

                status = 'stable'
                if new_price < old_price:
                    status = 'dropped'
                elif new_price > old_price:
                    status = 'increased'

                with transaction.atomic():
                    # 1. ÜRÜN KARTINI GÜNCELLE
                    product.last_status = status
                    product.current_price = new_price
                    # Son kontrol tarihini manuel olarak güncelliyoruz
                    product.last_checked = current_now

                    if new_data.get('original_price'):
                        product.original_price = Decimal(str(new_data['original_price']))

                    if status != 'stable':
                        product.previous_price = old_price

                    product.save()

                    # 2. TARİHÇEYE KAYIT AT (Bu kısım eksikti)
                    # Eğer fiyat değiştiyse VEYA hiç geçmiş kaydı yoksa ekle
                    if status != 'stable' or not product.history.exists():
                        PriceHistory.objects.create(
                            product=product,
                            price=new_price,
                            date=current_now  # Tarihi elle gönderiyoruz
                        )

                updated_count += 1

                # Mail Kuyruğu (Değişmedi)
                if status in ['dropped', 'increased'] and product.notification_email:
                    email = product.notification_email
                    if email not in email_queue:
                        email_queue[email] = {'dropped': [], 'increased': []}
                    email_queue[email][status].append({
                        'name': product.product_name,
                        'url': product.url,
                        'old': old_price,
                        'new': new_price
                    })

        # --- MAİL GÖNDERİMİ ---
        if email_queue:
            yield json.dumps({'status': 'mailing', 'message': 'Mailler gönderiliyor...', 'percent': 95}) + "\n"

            from django.core.mail import get_connection, EmailMultiAlternatives
            connection = get_connection()
            try:
                connection.open()
                print(f"✅ Mail sunucusuna bağlantı başarılı (smtp.gmail.com:587)")
            except Exception as conn_err:
                print(f"❌ Mail sunucu bağlantı hatası: {conn_err}")
                connection = None

            for email, changes in email_queue.items():
                subject = "🔔 Fiyat Takibi Bildirimi"
                
                # --- Plain Text Body ---
                message_body = "Merhaba,\n\nTakip listenizdeki bazı ürünlerde fiyat değişikliği oldu:\n\n"
                
                # --- HTML Body ---
                html_body = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; background-color: #f9f9f9;">
                    <h2 style="color: #333; text-align: center;">🔔 Fiyat Takibi Bildirimi</h2>
                    <p style="color: #555; font-size: 16px;">Merhaba,</p>
                    <p style="color: #555; font-size: 16px;">Takip listenizdeki ürünlerde yeni fiyat hareketleri tespit ettik.</p>
                """

                has_content = False

                if changes['dropped']:
                    has_content = True
                    message_body += "⬇️ FİYATI DÜŞENLER:\n"
                    html_body += """
                    <div style="margin-top: 20px; background-color: #d4edda; padding: 15px; border-radius: 8px; border-left: 5px solid #28a745;">
                        <h3 style="margin-top: 0; color: #155724;">⬇️ Fiyatı Düşen Ürünler</h3>
                        <ul style="padding-left: 20px;">
                    """
                    
                    for item in changes['dropped']:
                        # Text format
                        message_body += f"- {item['name']}\n  Eski: {item['old']} TL -> Yeni: {item['new']} TL\n  Link: {item['url']}\n\n"
                        
                        # HTML format
                        html_body += f"""
                        <li style="margin-bottom: 10px; color: #333;">
                            <strong>{item['name']}</strong><br>
                            <span style="text-decoration: line-through; color: #777;">{item['old']} TL</span> 
                            <span style="font-weight: bold; color: #28a745;">&nbsp;➝&nbsp; {item['new']} TL</span><br>
                            <a href="{item['url']}" style="display: inline-block; margin-top: 5px; color: #007bff; text-decoration: none; font-size: 14px;">👉 Ürüne Git</a>
                        </li>
                        """
                    html_body += "</ul></div>"

                if changes['increased']:
                    has_content = True
                    message_body += "⬆️ FİYATI ARTANLAR:\n"
                    html_body += """
                    <div style="margin-top: 20px; background-color: #f8d7da; padding: 15px; border-radius: 8px; border-left: 5px solid #dc3545;">
                        <h3 style="margin-top: 0; color: #721c24;">⬆️ Fiyatı Artan Ürünler</h3>
                        <ul style="padding-left: 20px;">
                    """

                    for item in changes['increased']:
                        # Text format
                        message_body += f"- {item['name']}\n  Eski: {item['old']} TL -> Yeni: {item['new']} TL\n  Link: {item['url']}\n\n"
                        
                        # HTML format
                        html_body += f"""
                        <li style="margin-bottom: 10px; color: #333;">
                            <strong>{item['name']}</strong><br>
                            <span style="text-decoration: line-through; color: #777;">{item['old']} TL</span> 
                            <span style="font-weight: bold; color: #dc3545;">&nbsp;➝&nbsp; {item['new']} TL</span><br>
                            <a href="{item['url']}" style="display: inline-block; margin-top: 5px; color: #007bff; text-decoration: none; font-size: 14px;">👉 Ürüne Git</a>
                        </li>
                        """
                    html_body += "</ul></div>"

                # Footer
                html_body += """
                    <div style="margin-top: 30px; text-align: center; font-size: 12px; color: #aaa;">
                        <p>Bu mail otomatik olarak gönderilmiştir. <br> Keyifli alışverişler!</p>
                    </div>
                </div>
                """

                if has_content and connection:
                    try:
                        msg = EmailMultiAlternatives(subject, message_body, settings.EMAIL_HOST_USER, [email],
                                                     connection=connection)
                        msg.attach_alternative(html_body, "text/html")
                        msg.send(fail_silently=False)
                        print(f"✅ Mail gönderildi: {email}")
                    except Exception as e:
                        print(f"❌ Mail hatası ({email}): {e}")
                elif has_content and not connection:
                    print(f"⚠️ Mail gönderilemedi ({email}): Sunucu bağlantısı yok")

            if connection:
                connection.close()

        yield json.dumps({
            'status': 'finished',
            'message': f'Tamamlandı! {updated_count} ürün güncellendi.',
            'percent': 100
        }) + "\n"

    return StreamingHttpResponse(event_stream(), content_type='application/x-ndjson')


# ============================================================
# MEDIA DOWNLOADER VIEWS
# ============================================================

@login_required
def media_downloader_dashboard(request):
    """Ana medya indirici sayfası"""
    return render(request, 'core/media_downloader.html')


@login_required
@require_POST
def download_media(request):
    """Video/ses indirme endpoint'i with quality options"""
    try:
        data = json.loads(request.body)
        url = data.get('url', '').strip()
        format_type = data.get('format', 'video')  # 'video' veya 'audio'
        quality = data.get('quality', '1080')  # Video: 2160/1440/1080/720/480/360, Audio: 320/192/128/64
        
        if not url:
            return JsonResponse({'error': 'URL gerekli!'}, status=400)
        
        # Geçici dosya için unique isim oluştur
        unique_id = str(uuid.uuid4())[:8]
        temp_dir = tempfile.gettempdir()
        
        # yt-dlp temel ayarları
        base_opts = {
            'outtmpl': os.path.join(temp_dir, f'{unique_id}.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            'socket_timeout': 60,
            'retries': 10,
            'fragment_retries': 10,
            'extractor_retries': 5,
            'file_access_retries': 5,
            'skip_unavailable_fragments': True,
            'ignoreerrors': False,
        }
        
        # Format ayarları
        if format_type == 'audio':
            audio_quality = quality if quality in ['320', '192', '128', '64'] else '192'
            base_opts['format'] = 'bestaudio/best'
            base_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': audio_quality,
            }]
            expected_ext = 'mp3'
        else:
            video_quality = quality if quality in ['2160', '1440', '1080', '720', '480', '360'] else '1080'
            # YouTube için daha stabil: tek akış formatı
            # Kalite sınırı tercih olarak belirtiliyor
            base_opts['format'] = f'best[height<={video_quality}]/best'
            base_opts['merge_output_format'] = 'mp4'
            expected_ext = 'mp4'
        
        # YouTube URL'si için özel ayarlar
        is_youtube = 'youtube.com' in url or 'youtu.be' in url
        if is_youtube:
            base_opts['extractor_args'] = {'youtube': {'player_client': ['ios']}}
            base_opts['nocheckcertificate'] = True
        
        # İndir
        try:
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.DownloadError as e:
            # iOS başarısız olursa android dene
            if is_youtube:
                base_opts['extractor_args'] = {'youtube': {'player_client': ['android']}}
                try:
                    with yt_dlp.YoutubeDL(base_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                except yt_dlp.DownloadError:
                    # Son çare: herhangi bir format
                    base_opts['format'] = 'best'
                    del base_opts['extractor_args']
                    with yt_dlp.YoutubeDL(base_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
            else:
                raise e
        
        title = info.get('title', 'media')
        
        # Dosya yolunu bul
        if format_type == 'audio':
            file_path = os.path.join(temp_dir, f'{unique_id}.mp3')
        else:
            # Video için farklı uzantılar olabilir
            for ext in ['mp4', 'webm', 'mkv']:
                potential_path = os.path.join(temp_dir, f'{unique_id}.{ext}')
                if os.path.exists(potential_path):
                    file_path = potential_path
                    expected_ext = ext
                    break
            else:
                file_path = os.path.join(temp_dir, f'{unique_id}.mp4')
        
        if not os.path.exists(file_path):
            return JsonResponse({'error': 'Dosya indirilemedi!'}, status=500)
        
        # Dosya boyutunu al
        file_size = os.path.getsize(file_path)
        
        # Güvenli dosya adı oluştur
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        
        # Kalite bilgisini dosya adına ekle
        if format_type == 'video':
            filename = f"{safe_title}_{video_quality}p.{expected_ext}"
        else:
            filename = f"{safe_title}_{audio_quality}kbps.{expected_ext}"
        
        # Dosyayı response olarak gönder
        response = FileResponse(
            open(file_path, 'rb'),
            as_attachment=True,
            filename=filename
        )
        response['Content-Length'] = file_size
        
        return response
        
    except yt_dlp.DownloadError as e:
        error_msg = str(e)
        if 'Video unavailable' in error_msg:
            return JsonResponse({'error': 'Video bulunamadı veya erişilemiyor!'}, status=400)
        elif 'Private video' in error_msg:
            return JsonResponse({'error': 'Bu video özel, indirilemez!'}, status=400)
        else:
            return JsonResponse({'error': f'İndirme hatası: {error_msg[:100]}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Bir hata oluştu: {str(e)[:100]}'}, status=500)


# ============================================================
# DECISION MAKER VIEWS
# ============================================================

@login_required
def decision_maker_dashboard(request):
    """Ana karar verici sayfası"""
    saved_wheels = DecisionWheel.objects.filter(user=request.user, is_template=False)
    template_wheels = DecisionWheel.objects.filter(is_template=True)
    recent_decisions = DecisionHistory.objects.filter(user=request.user)[:10]
    
    return render(request, 'core/decision_maker.html', {
        'saved_wheels': saved_wheels,
        'template_wheels': template_wheels,
        'recent_decisions': recent_decisions,
    })


@login_required
@require_POST
def save_wheel(request):
    """Çarkı kaydet (AJAX)"""
    try:
        data = json.loads(request.body)
        name = data.get('name', 'Yeni Çark')
        options = data.get('options', [])
        
        if len(options) < 2:
            return JsonResponse({'success': False, 'error': 'En az 2 seçenek gerekli!'}, status=400)
        
        wheel = DecisionWheel.objects.create(user=request.user, name=name)
        
        for i, opt in enumerate(options):
            WheelOption.objects.create(
                wheel=wheel,
                text=opt.get('text', ''),
                color=opt.get('color', '#667eea'),
                order=i
            )
        
        return JsonResponse({'success': True, 'id': wheel.id, 'name': wheel.name})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def get_wheel(request, id):
    """Kayıtlı çarkı getir (AJAX)"""
    wheel = get_object_or_404(DecisionWheel, id=id)
    
    # Eğer şablon değilse sadece sahibi görebilir
    if not wheel.is_template and wheel.user != request.user:
        return JsonResponse({'error': 'Yetkisiz erişim!'}, status=403)
    
    options = list(wheel.options.values('text', 'color', 'order'))
    return JsonResponse({
        'id': wheel.id,
        'name': wheel.name,
        'options': options
    })


@login_required
def delete_wheel(request, id):
    """Çarkı sil"""
    wheel = get_object_or_404(DecisionWheel, id=id, user=request.user)
    wheel.delete()
    return redirect('decision_maker')


@login_required
@require_POST
def save_decision_history(request):
    """Kararı geçmişe kaydet (AJAX)"""
    try:
        data = json.loads(request.body)
        DecisionHistory.objects.create(
            user=request.user,
            wheel_name=data.get('wheel_name', 'Adsız'),
            result=data.get('result', '')
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ============================================================
# WATCH TRACKER VIEWS
# ============================================================

@login_required
def watch_tracker_dashboard(request):
    """Main watch tracker page with all items"""
    items = WatchItem.objects.filter(user=request.user)
    
    # Segmentation by status
    ongoing = items.filter(status='ongoing')
    completed = items.filter(status='completed')
    planning = items.filter(status='planning')
    paused = items.filter(status='paused')
    
    # Statistics
    stats = {
        'total_completed': completed.count(),
        'movies_watched': completed.filter(item_type='movie').count(),
        'series_watched': completed.filter(item_type='series').count(),
        'books_read': completed.filter(item_type='book').count(),
        'currently_watching': ongoing.count(),
        'total_items': items.count(),
    }
    
    # Filter by type if requested
    filter_type = request.GET.get('type')
    if filter_type:
        items = items.filter(item_type=filter_type)
    
    context = {
        'items': items,
        'ongoing': ongoing,
        'completed': completed,
        'planning': planning,
        'paused': paused,
        'stats': stats,
        'filter_type': filter_type,
    }
    return render(request, 'core/watch_tracker_netflix.html', context)


@login_required
@require_POST
def add_watch_item(request):
    """Add new watch item (AJAX)"""
    try:
        data = json.loads(request.body)
        
        item = WatchItem.objects.create(
            user=request.user,
            title=data.get('title'),
            item_type=data.get('item_type'),
            genre=data.get('genre', ''),
            creator=data.get('creator', ''),
            year=data.get('year'),
            total_episodes=data.get('total_episodes'),
            total_pages=data.get('total_pages'),
            poster_url=data.get('poster_url', ''),
            is_shared=data.get('is_shared', False),
        )
        
        return JsonResponse({
            'success': True,
            'id': item.id,
            'title': item.title
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def watch_item_detail(request, id):
    """View/edit individual watch item"""
    item = get_object_or_404(WatchItem, id=id, user=request.user)
    
    if request.method == 'POST':
        # Update item
        item.status = request.POST.get('status', item.status)
        item.rating = request.POST.get('rating', item.rating)
        item.review = request.POST.get('review', item.review)
        item.current_episode = request.POST.get('current_episode', item.current_episode)
        item.current_page = request.POST.get('current_page', item.current_page)
        
        # Auto-complete if finished
        if item.item_type in ['series', 'podcast', 'documentary']:
            if item.total_episodes and int(item.current_episode) >= item.total_episodes:
                item.status = 'completed'
                item.completed_at = timezone.now()
        elif item.item_type == 'book':
            if item.total_pages and int(item.current_page) >= item.total_pages:
                item.status = 'completed'
                item.completed_at = timezone.now()
        
        item.save()
        messages.success(request, 'Güncellendi!')
        return redirect('watch_item_detail', id=id)
    
    context = {'item': item}
    return render(request, 'core/watch_item_detail.html', context)


@login_required
def get_watch_item_json(request, id):
    """API endpoint to get item details as JSON for modal"""
    item = get_object_or_404(WatchItem, id=id, user=request.user)
    
    return JsonResponse({
        'id': item.id,
        'title': item.title,
        'backdrop_url': item.backdrop_url or '',
        'poster_url': item.poster_url or '',
        'overview': item.overview or '',
        'year': item.year,
        'rating': item.rating,
        'status': item.status,
        'status_display': item.get_status_display(),
        'item_type': item.item_type,
        'item_type_display': item.get_item_type_display(),
        'current_episode': item.current_episode or 0,
        'total_episodes': item.total_episodes or 0,
        'current_page': item.current_page or 0,
        'total_pages': item.total_pages or 0,
        'progress_percentage': item.progress_percentage,
        'review': item.review or '',
    })


@login_required
@require_POST
def update_watch_item_json(request, id):
    """API endpoint to update item via AJAX"""
    item = get_object_or_404(WatchItem, id=id, user=request.user)
    
    try:
        data = json.loads(request.body)
        
        # Update fields
        if 'status' in data:
            item.status = data['status']
        if 'rating' in data:
            item.rating = data['rating'] if data['rating'] else None
        if 'review' in data:
            item.review = data['review']
        if 'current_episode' in data:
            item.current_episode = data['current_episode']
        if 'current_page' in data:
            item.current_page = data['current_page']
        
        # Auto-complete logic
        if item.item_type in ['series', 'podcast', 'documentary']:
            if item.total_episodes and item.current_episode >= item.total_episodes:
                item.status = 'completed'
                item.completed_at = timezone.now()
        elif item.item_type == 'book':
            if item.total_pages and item.current_page >= item.total_pages:
                item.status = 'completed'
                item.completed_at = timezone.now()
        
        item.save()
        
        return JsonResponse({
            'success': True,
            'item': {
                'id': item.id,
                'progress_percentage': item.progress_percentage,
                'rating': item.rating,
                'status': item.status,
                'status_display': item.get_status_display(),
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def delete_watch_item_json(request, id):
    """Delete watch item via AJAX - for modal delete button"""
    if request.method != 'DELETE':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        item = get_object_or_404(WatchItem, id=id, user=request.user)
        item_title = item.title
        item.delete()
        return JsonResponse({'success': True, 'message': f'{item_title} silindi'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def update_watch_progress(request, id):
    """Ajax endpoint to update progress"""
    item = get_object_or_404(WatchItem, id=id, user=request.user)
    
    try:
        data = json.loads(request.body)
        
        if 'episode' in data:
            item.current_episode = data['episode']
        if 'page' in data:
            item.current_page = data['page']
        if 'status' in data:
            item.status = data['status']
            
        item.save()
        
        return JsonResponse({
            'success': True,
            'progress': item.progress_percentage,
            'is_completed': item.is_completed
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def delete_watch_item(request, id):
    """Delete watch item"""
    item = get_object_or_404(WatchItem, id=id, user=request.user)
    item.delete()
    messages.success(request, f'{item.title} silindi.')
    return redirect('watch_tracker')


# ============================================================
# PLACE ARCHIVE VIEWS
# ============================================================

@login_required
def place_archive_dashboard(request):
    """Main restaurant/place archive"""
    places = Place.objects.filter(user=request.user).order_by('-average_rating')
    
    # Filter by category if requested
    category_filter = request.GET.get('category')
    if category_filter:
        places = places.filter(category=category_filter)
    
    # Statistics
    all_visits = PlaceVisit.objects.filter(user=request.user)
    stats = {
        'total_places': places.count(),
        'total_visits': all_visits.count(),
        'favorite_count': places.filter(visits__is_favorite=True).distinct().count(),
        'total_spent': all_visits.aggregate(Sum('cost'))['cost__sum'] or 0,
        'average_rating': places.aggregate(models.Avg('average_rating'))['average_rating__avg'] or 0,
    }
    
    # Top cuisine type
    top_cuisine = places.values('cuisine_type').annotate(
        count=models.Count('id')
    ).order_by('-count').first()
    if top_cuisine:
        stats['top_cuisine'] = top_cuisine['cuisine_type']
        stats['top_cuisine_count'] = top_cuisine['count']
    
    # Map data (for visualization)
    map_data = []
    for place in places.filter(latitude__isnull=False):
        map_data.append({
            'id': place.id,
            'name': place.name,
            'lat': float(place.latitude),
            'lng': float(place.longitude),
            'rating': float(place.average_rating),
            'category': place.category,
        })
    
    context = {
        'places': places,
        'stats': stats,
        'map_data': json.dumps(map_data),
        'category_filter': category_filter,
    }
    return render(request, 'core/place_archive.html', context)


@login_required
@require_POST
def add_place_visit(request):
    """Add new place visit"""
    try:
        # Check if place exists or create new
        place_name = request.POST.get('place_name')
        place_id = request.POST.get('place_id')
        
        if place_id:
            place = get_object_or_404(Place, id=place_id, user=request.user)
        else:
            # Create new place
            place = Place.objects.create(
                user=request.user,
                name=place_name,
                category=request.POST.get('category', 'restaurant'),
                cuisine_type=request.POST.get('cuisine_type', ''),
                address=request.POST.get('address', ''),
                city=request.POST.get('city', 'İstanbul'),
                district=request.POST.get('district', ''),
                price_range=int(request.POST.get('price_range', 2)),
                phone=request.POST.get('phone', ''),
            )
        
        # Create visit
        visit = PlaceVisit.objects.create(
            place=place,
            user=request.user,
            visit_date=request.POST.get('visit_date', timezone.now().date()),
            rating=request.POST.get('rating'),
            cost=request.POST.get('cost', 0),
            notes=request.POST.get('notes', ''),
            what_we_ate=request.POST.get('what_we_ate', ''),
            would_return=request.POST.get('would_return', 'on') == 'on',
            is_favorite=request.POST.get('is_favorite', 'off') == 'on',
        )
        
        # Handle photo uploads
        if 'photo1' in request.FILES:
            visit.photo1 = request.FILES['photo1']
        if 'photo2' in request.FILES:
            visit.photo2 = request.FILES['photo2']
        if 'photo3' in request.FILES:
            visit.photo3 = request.FILES['photo3']
        
        visit.save()
        messages.success(request, f'{place.name} ziyareti eklendi!')
        return redirect('place_archive')
        
    except Exception as e:
        messages.error(request, f'Hata: {str(e)}')
        return redirect('place_archive')


@login_required
def place_detail(request, id):
    """View individual place with visit history"""
    place = get_object_or_404(Place, id=id, user=request.user)
    visits = place.visits.all().order_by('-visit_date')
    
    context = {
        'place': place,
        'visits': visits,
    }
    return render(request, 'core/place_detail.html', context)


@login_required
def delete_place(request, id):
    """Delete place and all visits"""
    place = get_object_or_404(Place, id=id, user=request.user)
    place_name = place.name
    place.delete()
    messages.success(request, f'{place_name} silindi.')
    return redirect('place_archive')


# ============================================================
# RECOMMENDATION ENGINE
# ============================================================

def calculate_similarity_score(place1, place2):
    """Calculate similarity between two places (0-100 score)"""
    score = 0.0
    
    # Same cuisine: +40 points
    if place1.cuisine_type and place2.cuisine_type:
        if place1.cuisine_type.lower() == place2.cuisine_type.lower():
            score += 40
    
    # Similar price range: +20 points (max)
    price_diff = abs(place1.price_range - place2.price_range)
    score += max(0, 20 - (price_diff * 10))
    
    # Similar rating: +20 points (max)
    if place1.average_rating > 0 and place2.average_rating > 0:
        rating_diff = abs(place1.average_rating - place2.average_rating)
        score += max(0, 20 - (rating_diff * 4))
    
    # Close location (same district): +20 points
    if place1.district and place2.district:
        if place1.district.lower() == place2.district.lower():
            score += 20
    
    return round(score, 2)


def query_google_places(lat, lng, cuisine, radius=5000):
    """Query Google Places API for recommendations"""
    import requests
    from django.conf import settings
    
    # Check if API key is configured
    api_key = getattr(settings, 'GOOGLE_PLACES_API_KEY', None)
    if not api_key:
        return []
    
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f"{lat},{lng}",
        'radius': radius,
        'type': 'restaurant',
        'keyword': cuisine,
        'key': api_key,
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = []
            
            for item in data.get('results', [])[:5]:
                results.append({
                    'name': item['name'],
                    'address': item.get('vicinity', ''),
                    'rating': item.get('rating', 0),
                    'price_level': item.get('price_level', 2),
                    'source': 'google',
                    'score': item.get('rating', 0) * 10,  # Normalize to 0-50
                    'google_place_id': item['place_id'],
                    'lat': item['geometry']['location']['lat'],
                    'lng': item['geometry']['location']['lng'],
                })
            
            return results
    except Exception as e:
        print(f"Google Places API error: {e}")
    
    return []


def generate_recommendations(place, user):
    """
    Hybrid recommendation algorithm:
    1. Internal: Find similar places in user's database
    2. External: Query Google Places API for nearby similar venues
    """
    recommendations = []
    
    # INTERNAL: Content-based filtering
    similar_places = Place.objects.filter(
        user=user,
        cuisine_type__iexact=place.cuisine_type  # Case-insensitive
    ).exclude(id=place.id).order_by('-average_rating')[:5]
    
    for similar in similar_places:
        score = calculate_similarity_score(place, similar)
        if score > 30:  # Only recommend if similarity > 30%
            recommendations.append({
                'name': similar.name,
                'cuisine': similar.cuisine_type,
                'rating': float(similar.average_rating),
                'address': similar.address,
                'source': 'internal',
                'score': score,
                'place_id': similar.id,
            })
    
    # EXTERNAL: Google Places API (if enabled and location available)
    if place.latitude and place.longitude:
        external_recs = query_google_places(
            lat=float(place.latitude),
            lng=float(place.longitude),
            cuisine=place.cuisine_type
        )
        recommendations.extend(external_recs)
    
    # Sort by score and return top 8
    recommendations.sort(key=lambda x: x.get('score', 0), reverse=True)
    return recommendations[:8]


@login_required
def get_place_recommendations(request, place_id):
    """Get similar place recommendations (AJAX)"""
    place = get_object_or_404(Place, id=place_id, user=request.user)
    
    # Check cache first (24 hour validity)
    cache_validity = timezone.now() - timedelta(hours=24)
    cached = PlaceRecommendation.objects.filter(
        source_place=place,
        created_at__gte=cache_validity
    )[:8]
    
    if cached.exists():
        # Use cached recommendations
        recommendations = [rec.get_data() for rec in cached]
    else:
        # Generate new recommendations
        recommendations = generate_recommendations(place, request.user)
        
        # Clear old cache
        PlaceRecommendation.objects.filter(source_place=place).delete()
        
        # Cache results
        for rec in recommendations:
            cache_obj = PlaceRecommendation(
                source_place=place,
                similarity_score=rec.get('score', 0)
            )
            cache_obj.set_data(rec)  # Use helper method
            cache_obj.save()
    
    return JsonResponse({'recommendations': recommendations})


# ============================================================
# DEDICATED ADD PAGES & API ENDPOINTS (REDESIGN)
# ============================================================

@login_required
def add_watch_item_page(request):
    """Dedicated page for adding watch items with OMDb + TVMaze hybrid search"""
    if request.method == 'POST':
        # Create item with hybrid API data (OMDb or TVMaze)
        item_type = request.POST.get('item_type', 'movie')
        # Map API types to our types
        if item_type == 'tv':
            item_type = 'series'
        
        # Handle tmdb_id safely - hybrid API doesn't use it
        # Get tmdb_id if provided, otherwise None (not 'undefined' string)
        tmdb_id_value = request.POST.get('tmdb_id', '')
        if tmdb_id_value and tmdb_id_value != 'undefined' and tmdb_id_value.isdigit():
            tmdb_id = int(tmdb_id_value)
        else:
            tmdb_id = None
        
        item = WatchItem.objects.create(
            user=request.user,
            title=request.POST.get('title'),
            item_type=item_type,
            year=request.POST.get('year') or None,
            creator=request.POST.get('creator', ''),
            genre=request.POST.get('genre', ''),
            overview=request.POST.get('overview', ''),
            poster_url=request.POST.get('poster_url', ''),
            backdrop_url=request.POST.get('backdrop_url', ''),
            tmdb_id=tmdb_id,  # Now safely handled
            total_episodes=request.POST.get('total_episodes') or None,
            is_shared=request.POST.get('is_shared') == 'on',
        )
        
        messages.success(request, f'{item.title} eklendi!')
        return redirect('watch_tracker')
    
    return render(request, 'core/add_watch_item.html')


@login_required
def search_tmdb_ajax(request):
    """AJAX endpoint for OMDb + TVMaze hybrid search"""
    from .media_api import search_multi
    
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'results': []})
    
    results = search_multi(query)
    return JsonResponse({'results': results})


@login_required
def add_place_visit_page(request):
    """Dedicated page for adding place visits with Unsplash photos"""
    from datetime import date
    
    if request.method == 'POST':
        # Check if place exists or create new
        place_name = request.POST.get('place_name')
        
        # Create new place with Unsplash photo
        place = Place.objects.create(
            user=request.user,
            name=place_name,
            category=request.POST.get('category', 'restaurant'),
            cuisine_type=request.POST.get('cuisine_type', ''),
            address=request.POST.get('address', ''),
            city=request.POST.get('city', 'İstanbul'),
            district=request.POST.get('district', ''),
            price_range=int(request.POST.get('price_range', 2)),
            photo_url=request.POST.get('photo_url', ''),
            photo_photographer=request.POST.get('photo_photographer', ''),
            unsplash_id=request.POST.get('unsplash_id', ''),
        )
        
        # Create visit
        PlaceVisit.objects.create(
            place=place,
            user=request.user,
            visit_date=request.POST.get('visit_date', date.today()),
            rating=request.POST.get('rating'),
            cost=request.POST.get('cost', 0),
            notes=request.POST.get('notes', ''),
            what_we_ate=request.POST.get('what_we_ate', ''),
            would_return=request.POST.get('would_return', 'on') == 'on',
            is_favorite=request.POST.get('is_favorite', 'off') == 'on',
        )
        
        messages.success(request, f'{place.name} ziyareti eklendi!')
        return redirect('place_archive')
    
    context = {
        'today': date.today().isoformat()
    }
    return render(request, 'core/add_place_visit.html', context)


@login_required
def fetch_place_photos_ajax(request):
    """AJAX endpoint for fetching multiple Unsplash photos"""
    from .unsplash_api import get_multiple_photos
    
    cuisine = request.GET.get('cuisine', 'food')
    print(f"📸 Fetching photos for cuisine: {cuisine}")  # Debug log
    
    try:
        photos = get_multiple_photos(cuisine, count=6)
        print(f"📸 Found {len(photos)} photos")  # Debug log
        
        if not photos:
            print("⚠️ No photos returned from Unsplash API")  # Debug log
            
        return JsonResponse({'photos': photos})
    except Exception as e:
        print(f"❌ Error fetching photos: {e}")  # Debug log
        import traceback
        traceback.print_exc()
        return JsonResponse({'photos': [], 'error': str(e)})
