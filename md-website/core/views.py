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

            # Trendyol kontrolü
            if "trendyol" in url:
                messages.error(request, "Trendyol şu an desteklenmemektedir.")
                return redirect('price_tracking_dashboard')

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
                    seller_name=scraped_data['seller']
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
                subject = "🔔 Fiyat Takip Bildirimi"
                
                # --- Plain Text Body ---
                message_body = "Merhaba,\n\nTakip listenizdeki bazı ürünlerde fiyat değişikliği oldu:\n\n"
                
                # --- HTML Body ---
                html_body = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; background-color: #f9f9f9;">
                    <h2 style="color: #333; text-align: center;">🔔 Fiyat Takip Bildirimi</h2>
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
