"""
Background price checking function
Separated from views for scheduler use
"""
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.core.mail import get_connection, EmailMultiAlternatives


def check_all_prices():
    """
    Background job: Check all tracked products and update prices
    This runs automatically every 5 minutes (test) or manually via button
    """
    from .models import TrackedProduct, PriceHistory
    from .utils import get_product_details
    
    products = list(TrackedProduct.objects.all())
    total_products = len(products)
    
    if total_products == 0:
        print("   Takip edilen ürün yok.")
        return
    
    print(f"   {total_products} ürün taranacak...")
    
    email_queue = {}
    updated_count = 0
    
    for index, product in enumerate(products, 1):
        print(f"   [{index}/{total_products}] {product.product_name} ({product.site_name})")
        
        try:
            new_data = get_product_details(product.url)
        except Exception as e:
            print(f"      ⚠️ Hata: {e}")
            new_data = None
        
        if new_data and new_data['price'] > 0:
            new_price = Decimal(str(new_data['price']))
            old_price = product.current_price
            
            current_now = timezone.now()
            
            status = 'stable'
            if new_price < old_price:
                status = 'dropped'
            elif new_price > old_price:
                status = 'increased'
            
            with transaction.atomic():
                # 1. ÜRÜN GÜNCELLE
                product.last_status = status
                product.current_price = new_price
                product.last_checked = current_now
                
                if new_data.get('original_price'):
                    product.original_price = Decimal(str(new_data['original_price']))
                
                if new_data.get('plus_price'):
                    product.plus_price = Decimal(str(new_data['plus_price']))
                
                if status != 'stable':
                    product.previous_price = old_price
                
                product.save()
                
                # 2. TARİHÇEYE KAYDET
                if status != 'stable' or not product.history.exists():
                    PriceHistory.objects.create(
                        product=product,
                        price=new_price,
                        date=current_now
                    )
            
            updated_count += 1
            
            if status == 'dropped':
                print(f"      ✅ Fiyat düştü: {old_price} → {new_price} ₺")
            elif status == 'increased':
                print(f"      ⬆️ Fiyat yükseldi: {old_price} → {new_price} ₺")
            else:
                print(f"      📊 Aynı: {new_price} ₺")
            
            # Mail kuyruğu
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
        print(f"   📧 {len(email_queue)} kişiye mail gönderiliyor...")
        
        connection = get_connection()
        try:
            connection.open()
        except:
            connection = None
        
        for email, changes in email_queue.items():
            subject = "🔔 Fiyat Takibi Bildirimi"
            
            # Plain text
            message_body = "Merhaba,\\n\\nTakip listenizdeki bazı ürünlerde fiyat değişikliği oldu:\\n\\n"
            
            # HTML
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #333;">🔔 Fiyat Takibi Bildirimi</h2>
                <p>Merhaba,</p>
                <p>Takip listenizdeki bazı ürünlerde fiyat değişikliği oldu:</p>
            """
            
            if changes['dropped']:
                html_body += '<h3 style="color: green;">📉 Fiyatı Düşen Ürünler</h3><ul>'
                for item in changes['dropped']:
                    message_body += f"✅ {item['name']}: {item['old']} → {item['new']} ₺\\n"
                    html_body += f'<li><strong>{item["name"]}</strong>: <span style="text-decoration: line-through;">{item["old"]} ₺</span> → <span style="color: green; font-weight: bold;">{item["new"]} ₺</span><br><a href="{item["url"]}">Ürüne Git</a></li>'
                html_body += '</ul>'
            
            if changes['increased']:
                html_body += '<h3 style="color: red;">📈 Fiyatı Yükselen Ürünler</h3><ul>'
                for item in changes['increased']:
                    message_body += f"⬆️ {item['name']}: {item['old']} → {item['new']} ₺\\n"
                    html_body += f'<li><strong>{item["name"]}</strong>: {item["old"]} ₺ → <span style="color: red; font-weight: bold;">{item["new"]} ₺</span><br><a href="{item["url"]}">Ürüne Git</a></li>'
                html_body += '</ul>'
            
            html_body += """
                <p>İyi alışverişler!</p>
            </body>
            </html>
            """
            
            try:
                msg = EmailMultiAlternatives(subject, message_body, to=[email], connection=connection)
                msg.attach_alternative(html_body, "text/html")
                msg.send()
                print(f"      ✉️ Mail gönderildi: {email}")
            except Exception as e:
                print(f"      ❌ Mail hatası ({email}): {e}")
        
        if connection:
            connection.close()
    
    print(f"   ✅ Tarama tamamlandı! {updated_count} ürün güncellendi.")
