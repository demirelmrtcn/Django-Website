from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from django.http import StreamingHttpResponse, FileResponse, JsonResponse
from django.db import transaction
from .models import Transaction, TrackedProduct, PriceHistory, Note, CalendarEvent, DecisionWheel, WheelOption, DecisionHistory
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

    # --- GRAFİK İÇİN VERİ HAZIRLIĞI ---
    # Her ürün için tarihçeyi çekip Chart.js formatına çevireceğiz
    chart_data = {
        'labels': [],  # Tarihler (Ortak eksen)
        'datasets': []
    }

    # Eğer ürün varsa grafik verisi oluştur
    if products.exists():
        # Grafik renkleri (Otomatik renk atamak için basit bir liste)
        colors = ['#0d6efd', '#dc3545', '#198754', '#ffc107', '#6f42c1', '#fd7e14', '#20c997']

        for i, product in enumerate(products):
            # Son 10 fiyat hareketini al
            history = product.history.all().order_by('date')[:10]

            data_points = []
            labels = []
            for h in history:
                data_points.append(float(h.price))
                # Tarih formatı: "22 Ara 14:30"
                labels.append(h.date.strftime('%d %b %H:%M'))

            chart_data['datasets'].append({
                'label': product.custom_name or product.product_name[:15],
                'data': data_points,
                'borderColor': colors[i % len(colors)],  # Renk sırasıyla
                'fill': False,
                'tension': 0.1
            })

            # Eksen etiketlerini (zamanı) son ürünün tarihine göre set edelim (Basit çözüm)
            if len(labels) > len(chart_data['labels']):
                chart_data['labels'] = labels

    context = {
        'products': products,
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


