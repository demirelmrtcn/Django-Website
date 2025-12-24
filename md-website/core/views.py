from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from django.http import StreamingHttpResponse
from django.db import transaction
from .models import Transaction, TrackedProduct, PriceHistory
from .forms import TransactionForm, AddProductForm
from .utils import get_product_details
import datetime
from dateutil.relativedelta import relativedelta
from django.urls import reverse
from django.core.mail import send_mail, get_connection, EmailMultiAlternatives
from django.conf import settings
from decimal import Decimal
import json

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
    }
    return render(request, 'core/price_tracking.html', context)


@login_required
def delete_product(request, id):
    product = get_object_or_404(TrackedProduct, id=id, user=request.user)
    product.delete()
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
            except:
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
                    except Exception as e:
                        print(f"Mail hatası: {e}")

            if connection:
                connection.close()

        yield json.dumps({
            'status': 'finished',
            'message': f'Tamamlandı! {updated_count} ürün güncellendi.',
            'percent': 100
        }) + "\n"

    return StreamingHttpResponse(event_stream(), content_type='application/x-ndjson')


# ============================================================
# ORGANIZER - NOTES & CALENDAR VIEWS
# ============================================================

from .models import Note, CalendarEvent
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
import json


@login_required
def organizer_dashboard(request):
    """Ana organizer sayfası - Notlar ve Takvim"""
    notes = Note.objects.filter(user=request.user)
    events = CalendarEvent.objects.filter(user=request.user)
    
    context = {
        'notes': notes,
        'events': events,
    }
    return render(request, 'core/organizer.html', context)


@login_required
@require_POST
def create_note(request):
    """Yeni not oluştur (AJAX)"""
    try:
        data = json.loads(request.body)
        note = Note.objects.create(
            user=request.user,
            title=data.get('title', 'Yeni Not'),
            content=data.get('content', ''),
            color=data.get('color', '#ffffff')
        )
        return JsonResponse({
            'success': True,
            'note': {
                'id': note.id,
                'title': note.title,
                'content': note.content,
                'color': note.color,
                'updated_at': note.updated_at.strftime('%d.%m.%Y %H:%M'),
                'is_pinned': note.is_pinned
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def update_note(request, id):
    """Not güncelle (AJAX)"""
    try:
        note = get_object_or_404(Note, id=id, user=request.user)
        data = json.loads(request.body)
        
        if 'title' in data:
            note.title = data['title']
        if 'content' in data:
            note.content = data['content']
        if 'color' in data:
            note.color = data['color']
        if 'is_pinned' in data:
            note.is_pinned = data['is_pinned']
        
        note.save()
        
        return JsonResponse({
            'success': True,
            'note': {
                'id': note.id,
                'title': note.title,
                'content': note.content,
                'color': note.color,
                'updated_at': note.updated_at.strftime('%d.%m.%Y %H:%M'),
                'is_pinned': note.is_pinned
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_GET
def get_note(request, id):
    """Tek not içeriğini getir (AJAX)"""
    try:
        note = get_object_or_404(Note, id=id, user=request.user)
        return JsonResponse({
            'success': True,
            'note': {
                'id': note.id,
                'title': note.title,
                'content': note.content,
                'color': note.color,
                'updated_at': note.updated_at.strftime('%d.%m.%Y %H:%M'),
                'is_pinned': note.is_pinned
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)



@login_required
@require_POST
def delete_note(request, id):
    """Not sil"""
    try:
        note = get_object_or_404(Note, id=id, user=request.user)
        note.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def create_event(request):
    """Takvim etkinliği oluştur (AJAX)"""
    try:
        data = json.loads(request.body)
        
        # Debug için yazdır
        print(f"DEBUG create_event data: {data}")
        
        # end_date boş string ise None yap
        end_date = data.get('end_date')
        if end_date == '' or end_date is None:
            end_date = None
        
        # start_date kontrolü
        start_date = data.get('start_date')
        if not start_date:
            return JsonResponse({'success': False, 'error': 'Başlangıç tarihi gerekli'}, status=400)
        
        event = CalendarEvent.objects.create(
            user=request.user,
            title=data.get('title', 'Yeni Etkinlik'),
            description=data.get('description', ''),
            start_date=start_date,
            end_date=end_date,
            event_type=data.get('event_type', 'event'),
            color=data.get('color', '#667eea'),
            all_day=data.get('all_day', True),
            is_recurring=data.get('is_recurring', False)
        )
        
        print(f"DEBUG created event: {event.id} - {event.title}")
        
        return JsonResponse({
            'success': True,
            'event': {
                'id': event.id,
                'title': event.title,
                'start': start_date,  # Zaten string formatında
                'end': end_date,  # Zaten string veya None
                'color': event.color,
                'allDay': event.all_day,
                'is_recurring': event.is_recurring
            }
        })

    except Exception as e:
        import traceback
        print(f"ERROR create_event: {e}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=400)




@login_required
@require_POST
def delete_event(request, id):
    """Etkinlik sil"""
    try:
        event = get_object_or_404(CalendarEvent, id=id, user=request.user)
        event.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_GET
def get_events(request):
    """Takvim etkinliklerini JSON olarak getir (FullCalendar için)"""
    from datetime import date, datetime
    
    events = CalendarEvent.objects.filter(user=request.user)
    
    # FullCalendar tarih aralığını al ve parse et
    start_param = request.GET.get('start', '')
    end_param = request.GET.get('end', '')
    
    # Tarih aralığını parse et (örn: 2025-11-30T00:00:00+03:00)
    try:
        if start_param:
            start_date = datetime.fromisoformat(start_param.replace('Z', '+00:00')).date()
        else:
            start_date = date.today().replace(day=1)
        
        if end_param:
            end_date = datetime.fromisoformat(end_param.replace('Z', '+00:00')).date()
        else:
            end_date = date.today().replace(day=28) + timedelta(days=35)
    except:
        start_date = date.today().replace(day=1)
        end_date = date.today().replace(day=28) + timedelta(days=35)
    
    # İstenen yılları hesapla
    years_in_range = set()
    current = start_date
    while current <= end_date:
        years_in_range.add(current.year)
        current = current.replace(year=current.year + 1) if current.month == 1 else current.replace(month=current.month + 1 if current.month < 12 else 1, year=current.year if current.month < 12 else current.year + 1)
    
    events_list = []
    for event in events:
        if event.is_recurring:
            # Tekrarlayan etkinlik: Sadece görüntülenen yıllar için
            original_month = event.start_date.month
            original_day = event.start_date.day
            
            for year in years_in_range:
                try:
                    recurring_date = date(year, original_month, original_day)
                    # Sadece aralık içindeyse ekle
                    if start_date <= recurring_date <= end_date:
                        events_list.append({
                            'id': f"{event.id}_{year}",
                            'title': f"🔄 {event.title}",
                            'start': recurring_date.isoformat(),
                            'end': None,
                            'color': event.color,
                            'allDay': event.all_day,
                            'extendedProps': {
                                'description': event.description,
                                'event_type': event.event_type,
                                'is_recurring': True,
                                'original_id': event.id
                            }
                        })
                except ValueError:
                    pass
        else:
            # Normal etkinlik - sadece aralık içindeyse
            event_date = event.start_date
            if start_date <= event_date <= end_date:
                events_list.append({
                    'id': event.id,
                    'title': event.title,
                    'start': event.start_date.isoformat(),
                    'end': event.end_date.isoformat() if event.end_date else None,
                    'color': event.color,
                    'allDay': event.all_day,
                    'extendedProps': {
                        'description': event.description,
                        'event_type': event.event_type,
                        'is_recurring': False
                    }
                })
    
    return JsonResponse(events_list, safe=False)


