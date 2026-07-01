import requests
import json
import base64
import re
import os
from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import Club, UserProfile
from urllib.parse import quote, unquote

# =====================================================
# === КАСТОМНЫЙ ВХОД
# =====================================================

def custom_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Если пользователь суперпользователь → на /admin/verify/
            if user.is_superuser:
                return redirect('admin_verify')
            # Если обычный пользователь → на /dashboard/
            else:
                return redirect('clubs:dashboard')
    else:
        form = AuthenticationForm()
    
    return render(request, 'registration/login.html', {'form': form})

# =====================================================
# === КОНСТАНТЫ ПОЛЕЙ БИТРИКС24
# =====================================================

BITRIX_FIELDS = {
    'rights': 'ufCrm8_1782371217',
    'umo': 'ufCrm8_1782742262',
    'insurance': 'ufCrm8_1782742287',
    'finance': 'ufCrm8_1782371217',  # ЗАМЕНИ НА РЕАЛЬНЫЙ КОД ПОЛЯ ДЛЯ ФИНАНСОВ
}

def get_bitrix_field(doc_type):
    return BITRIX_FIELDS.get(doc_type, BITRIX_FIELDS['rights'])

def normalize_filename(filename):
    name, ext = os.path.splitext(filename)
    name = re.sub(r'[^\w\s.-]', '', name)
    name = re.sub(r'\s+', ' ', name)
    if len(name) > 50:
        name = name[:50]
    name = name.strip()
    if not name:
        name = f"document_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return f"{name}{ext}"

def get_file_name_from_url(download_url):
    try:
        response = requests.get(download_url, stream=True)
        content_disposition = response.headers.get('Content-Disposition')
        if content_disposition:
            match = re.search(r"filename\*=utf-8''([^;]+)", content_disposition)
            if match:
                return unquote(match.group(1))
            match = re.search(r'filename="([^"]+)"', content_disposition)
            if match:
                return match.group(1)
        return None
    except Exception as e:
        print(f"Ошибка получения имени файла: {e}")
        return None

def get_file_info_from_bitrix(field_value):
    if not field_value or field_value == 0:
        return False, None, None
    
    download_url = None
    
    if isinstance(field_value, dict):
        download_url = field_value.get('urlMachine') or field_value.get('url') or None
    elif isinstance(field_value, list) and len(field_value) > 0:
        if isinstance(field_value[0], dict):
            download_url = field_value[0].get('urlMachine') or field_value[0].get('url') or None
    
    if not download_url:
        return False, None, None
    
    file_name = get_file_name_from_url(download_url)
    
    if not file_name:
        file_name = "document.pdf"
    
    return True, file_name, download_url

# =====================================================
# === СОЗДАНИЕ СДЕЛКИ В ВОРОНКЕ 33
# =====================================================

def create_medical_deal(rfs_id, sport_name, file_name, file_content, doc_type):
    """
    Создаёт сделку в воронке 33 с медицинским документом
    doc_type: 'umo' → 1, 'insurance' → 2
    Возвращает: (success, deal_id, error_message)
    """
    try:
        webhook = settings.BITRIX24_WEBHOOK
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        
        doc_type_value = 1 if doc_type == 'umo' else 2 if doc_type == 'insurance' else 0
        
        response = requests.post(
            webhook + "crm.deal.add",
            json={
                "fields": {
                    "TITLE": f"Мед. документы - {sport_name}",
                    "CATEGORY_ID": 33,
                    "STAGE_ID": "C33:NEW",
                    "UF_CRM_1782890524318": str(rfs_id),
                    "UF_CRM_1782890547596": sport_name,
                    "UF_CRM_1782890579348": {
                        "fileData": [file_name, file_base64]
                    },
                    "UF_CRM_1782890601789": "N",
                    "UF_CRM_1782894229856": doc_type_value
                }
            },
            timeout=30
        )
        
        data = response.json()
        
        if 'error' in data:
            return False, None, data.get('error')
        
        deal_id = data.get('result')
        return True, deal_id, None
        
    except Exception as e:
        return False, None, str(e)

# =====================================================
# === ОСНОВНЫЕ ФУНКЦИИ
# =====================================================

def index(request):
    if request.user.is_authenticated:
        return redirect('clubs:dashboard')
    return redirect('login')

@login_required
def dashboard(request):
    try:
        club = Club.objects.filter(user=request.user).first()
        if club:
            user_rights = 0
            if hasattr(request.user, 'profile'):
                user_rights = request.user.profile.rights
            return render(request, 'clubs/dashboard.html', {
                'club': club,
                'user_rights': user_rights
            })
        return render(request, 'clubs/dashboard.html', {'club': None, 'user_rights': 0})
    except Exception as e:
        print(f"Ошибка в dashboard: {e}")
        return render(request, 'clubs/dashboard.html', {'club': None, 'user_rights': 0})

# =====================================================
# === СДЕЛКИ
# =====================================================

@login_required
def get_deals(request):
    try:
        club = Club.objects.filter(user=request.user).first()
        if not club:
            return JsonResponse({'error': 'Клуб не найден'}, status=404)
        
        rfs_id = club.rfs_id
        if not rfs_id:
            return JsonResponse({'error': 'У клуба не указан РФС ID'}, status=400)
        
        webhook_url = "https://drlk.rfs.ru/rest/205/mkoe2cdimf6len15/"
        response = requests.post(
            webhook_url + "crm.deal.list",
            json={
                "filter": {"UF_CRM_DEAL_1773909250766": rfs_id, "CATEGORY_ID": 29},
                "select": [
                    "ID", "TITLE", "STAGE_ID", "DATE_CREATE",
                    "UF_CRM_DEAL_1773845091277", "UF_CRM_DEAL_1773845130405",
                    "UF_CRM_DEAL_1773909188274", "UF_CRM_DEAL_1773909250766",
                    "UF_CRM_DEAL_1773907718196", "UF_CRM_DEAL_1773914756198",
                    "UF_CRM_DEAL_1773914958204", "UF_CRM_DEAL_1774945121159"
                ]
            }
        )
        data = response.json()
        if 'result' not in data:
            return JsonResponse({'error': 'Ошибка получения данных из CRM'}, status=500)
        deals = data['result']
        for deal in deals:
            if deal.get('DATE_CREATE'):
                deal['DATE_CREATE'] = deal['DATE_CREATE'][:10]
        return JsonResponse({'deals': deals})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# =====================================================
# === ДОКУМЕНТЫ
# =====================================================

@login_required
def get_club_document(request):
    try:
        club = Club.objects.filter(user=request.user).first()
        if not club:
            return JsonResponse({'error': 'Клуб не найден'}, status=404)
        
        doc_type = request.GET.get('doc_type', 'rights')
        bitrix_field = get_bitrix_field(doc_type)
        
        if not club.rfs_id:
            return JsonResponse({'error': 'У клуба не указан РФС ID'}, status=400)
        
        webhook = settings.BITRIX24_WEBHOOK
        entity_type_id = settings.SMART_PROCESS_ID
        
        search_response = requests.post(
            webhook + "crm.item.list",
            json={
                "entityTypeId": entity_type_id,
                "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
            }
        )
        
        search_data = search_response.json()
        items = search_data.get('result', {}).get('items', [])
        
        if not items:
            return JsonResponse({'document': None})
        
        field_value = items[0].get(bitrix_field)
        has_file, file_name, download_url = get_file_info_from_bitrix(field_value)
        
        if has_file:
            return JsonResponse({
                'document': {
                    'id': doc_type,
                    'name': file_name,
                    'download_url': download_url,
                    'uploaded_at': datetime.now().strftime('%d.%m.%Y %H:%M')
                }
            })
        
        return JsonResponse({'document': None})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# =====================================================
# СКАЧИВАНИЕ ДЛЯ ТЕКУЩЕГО КЛУБА (из личного кабинета)
# =====================================================

@login_required
def download_club_document(request, doc_type):
    try:
        club = Club.objects.filter(user=request.user).first()
        if not club:
            return HttpResponse('Клуб не найден', status=404)
        
        bitrix_field = get_bitrix_field(doc_type)
        
        if not club.rfs_id:
            return HttpResponse('У клуба не указан РФС ID', status=400)
        
        webhook = settings.BITRIX24_WEBHOOK
        entity_type_id = settings.SMART_PROCESS_ID
        
        search_response = requests.post(
            webhook + "crm.item.list",
            json={
                "entityTypeId": entity_type_id,
                "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
            }
        )
        
        search_data = search_response.json()
        items = search_data.get('result', {}).get('items', [])
        
        if not items:
            return HttpResponse('Элемент не найден', status=404)
        
        field_value = items[0].get(bitrix_field)
        
        if not field_value or field_value == 0:
            return HttpResponse('Файл не найден', status=404)
        
        download_url = None
        
        if isinstance(field_value, dict):
            download_url = field_value.get('urlMachine') or field_value.get('url') or None
        elif isinstance(field_value, list) and len(field_value) > 0:
            if isinstance(field_value[0], dict):
                download_url = field_value[0].get('urlMachine') or field_value[0].get('url') or None
        
        if not download_url:
            return HttpResponse('Ссылка на файл не найдена', status=404)
        
        download_response = requests.get(download_url)
        
        if download_response.status_code != 200:
            return HttpResponse(f'Ошибка скачивания: {download_response.status_code}', status=500)
        
        content_disposition = download_response.headers.get('Content-Disposition')
        filename = None
        
        if content_disposition:
            match = re.search(r"filename\*=utf-8''([^;]+)", content_disposition)
            if match:
                filename = unquote(match.group(1))
            else:
                match = re.search(r'filename="([^"]+)"', content_disposition)
                if match:
                    filename = match.group(1)
        
        if not filename:
            filename = f"document_{doc_type}.pdf"
        
        content_type = 'application/octet-stream'
        if filename.endswith('.pdf'):
            content_type = 'application/pdf'
        elif filename.endswith('.docx'):
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif filename.endswith('.doc'):
            content_type = 'application/msword'
        
        encoded_filename = quote(filename)
        response = HttpResponse(download_response.content, content_type=content_type)
        response['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response['Content-Length'] = len(download_response.content)
        return response
        
    except Exception as e:
        return HttpResponse(str(e), status=500)

# =====================================================
# СКАЧИВАНИЕ ПО ID КЛУБА (из админ-панели)
# =====================================================

@login_required
def download_club_document_by_club(request, doc_type):
    """
    Скачивает документ клуба по ID (для админ-панели)
    """
    try:
        club_id = request.GET.get('club_id')
        if not club_id:
            return HttpResponse('Не указан ID клуба', status=400)
        
        club = Club.objects.get(id=club_id)
        bitrix_field = get_bitrix_field(doc_type)
        
        if not club.rfs_id:
            return HttpResponse('У клуба не указан РФС ID', status=400)
        
        webhook = settings.BITRIX24_WEBHOOK
        entity_type_id = settings.SMART_PROCESS_ID
        
        search_response = requests.post(
            webhook + "crm.item.list",
            json={
                "entityTypeId": entity_type_id,
                "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
            }
        )
        
        search_data = search_response.json()
        items = search_data.get('result', {}).get('items', [])
        
        if not items:
            return HttpResponse('Элемент не найден', status=404)
        
        field_value = items[0].get(bitrix_field)
        
        if not field_value or field_value == 0:
            return HttpResponse('Файл не найден', status=404)
        
        download_url = None
        
        if isinstance(field_value, dict):
            download_url = field_value.get('urlMachine') or field_value.get('url') or None
        elif isinstance(field_value, list) and len(field_value) > 0:
            if isinstance(field_value[0], dict):
                download_url = field_value[0].get('urlMachine') or field_value[0].get('url') or None
        
        if not download_url:
            return HttpResponse('Ссылка на файл не найдена', status=404)
        
        download_response = requests.get(download_url)
        
        if download_response.status_code != 200:
            return HttpResponse(f'Ошибка скачивания: {download_response.status_code}', status=500)
        
        content_disposition = download_response.headers.get('Content-Disposition')
        filename = None
        
        if content_disposition:
            match = re.search(r"filename\*=utf-8''([^;]+)", content_disposition)
            if match:
                filename = unquote(match.group(1))
            else:
                match = re.search(r'filename="([^"]+)"', content_disposition)
                if match:
                    filename = match.group(1)
        
        if not filename:
            filename = f"document_{doc_type}.pdf"
        
        content_type = 'application/octet-stream'
        if filename.endswith('.pdf'):
            content_type = 'application/pdf'
        elif filename.endswith('.docx'):
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif filename.endswith('.doc'):
            content_type = 'application/msword'
        
        encoded_filename = quote(filename)
        response = HttpResponse(download_response.content, content_type=content_type)
        response['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response['Content-Length'] = len(download_response.content)
        return response
        
    except Club.DoesNotExist:
        return HttpResponse('Клуб не найден', status=404)
    except Exception as e:
        return HttpResponse(str(e), status=500)

# =====================================================
# ПОЛУЧЕНИЕ ДАННЫХ КЛУБА
# =====================================================

@login_required
def get_club_data(request):
    try:
        club = Club.objects.filter(user=request.user).first()
        if not club:
            return JsonResponse({'error': 'Клуб не найден'}, status=404)
        
        if not club.rfs_id:
            return JsonResponse({'error': 'У клуба не указан РФС ID'}, status=400)
        
        webhook = settings.BITRIX24_WEBHOOK
        entity_type_id = settings.SMART_PROCESS_ID
        
        search_response = requests.post(
            webhook + "crm.item.list",
            json={
                "entityTypeId": entity_type_id,
                "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
            }
        )
        
        search_data = search_response.json()
        items = search_data.get('result', {}).get('items', [])
        
        if not items:
            return JsonResponse({'error': 'Элемент не найден'}, status=404)
        
        item = items[0]
        
        def has_file(field_value):
            if not field_value or field_value == 0:
                return False
            if isinstance(field_value, dict):
                return bool(field_value.get('id') or field_value.get('urlMachine'))
            if isinstance(field_value, list) and len(field_value) > 0:
                return True
            if isinstance(field_value, str) and field_value:
                return True
            return False
        
        data = {
            'sport_name': item.get('ufCrm8_1782379111', '') or '',
            'rfs_id': item.get('ufCrm8_1782372679', '') or '',
            'fifa_id': item.get('ufCrm8_1782378578', '') or '',
            'ogrn': item.get('ufCrm8_1782379087', '') or '',
            'email': item.get('ufCrm8_1782379155', '') or '',
            'aff_name': item.get('ufCrm8_1782379141', '') or '',
            'has_rights': has_file(item.get('ufCrm8_1782371217')),
            'has_umo': has_file(item.get('ufCrm8_1782742262')),
            'has_insurance': has_file(item.get('ufCrm8_1782742287')),
            'has_finance': has_file(item.get('ufCrm8_1782371217')),  # ЗАМЕНИ НА РЕАЛЬНОЕ ПОЛЕ
            'umo_verified': item.get('ufCrm8_1782815972') == 'Y',
            'insurance_verified': item.get('ufCrm8_1782815987') == 'Y',
        }
        
        return JsonResponse({'club': data})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# =====================================================
# ЗАГРУЗКА ДОКУМЕНТА
# =====================================================

@csrf_exempt
@login_required
def upload_club_document(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    try:
        club = Club.objects.filter(user=request.user).first()
        if not club:
            return JsonResponse({'error': 'Клуб не найден'}, status=404)
        
        file = request.FILES.get('document')
        doc_type = request.POST.get('doc_type', 'rights')
        bitrix_field = get_bitrix_field(doc_type)
        
        if not file:
            return JsonResponse({'error': 'Файл не выбран'}, status=400)
        
        if not club.rfs_id:
            return JsonResponse({'error': 'У клуба не указан РФС ID'}, status=400)
        
        ext = file.name.split('.')[-1].lower()
        if ext not in ['pdf', 'doc', 'docx']:
            return JsonResponse({'error': 'Только PDF или Word'}, status=400)
        
        if file.size > 50 * 1024 * 1024:
            return JsonResponse({'error': 'Файл больше 50 МБ'}, status=400)
        
        if len(file.name) > 100:
            return JsonResponse({'error': 'Имя файла слишком длинное (максимум 100 символов)'}, status=400)
        
        if re.search(r'[\\/:*?"<>|]', file.name):
            return JsonResponse({'error': 'Имя содержит запрещенные символы'}, status=400)
        
        original_name = file.name
        upload_name = normalize_filename(original_name)
        
        webhook = settings.BITRIX24_WEBHOOK
        entity_type_id = settings.SMART_PROCESS_ID
        
        file.seek(0)
        file_content = file.read()
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        
        # =============================================
        # ЕСЛИ ЭТО УМО ИЛИ СТРАХОВКА → СОЗДАЁМ СДЕЛКУ В ВОРОНКЕ 33
        # =============================================
        if doc_type in ['umo', 'insurance']:
            success, deal_id, error = create_medical_deal(
                rfs_id=club.rfs_id,
                sport_name=club.sport_name,
                file_name=upload_name,
                file_content=file_content,
                doc_type=doc_type
            )
            
            if not success:
                return JsonResponse({'error': f'Ошибка создания сделки: {error}'}, status=500)
            
            fields = {
                bitrix_field: [upload_name, file_base64]
            }
            
            if doc_type == 'umo':
                fields['ufCrm8_1782815972'] = 'N'
            elif doc_type == 'insurance':
                fields['ufCrm8_1782815987'] = 'N'
            
            search_response = requests.post(
                webhook + "crm.item.list",
                json={
                    "entityTypeId": entity_type_id,
                    "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
                }
            )
            
            search_data = search_response.json()
            items = search_data.get('result', {}).get('items', [])
            
            if items:
                item_id = items[0]['id']
                update_response = requests.post(
                    webhook + "crm.item.update",
                    json={
                        "entityTypeId": entity_type_id,
                        "id": item_id,
                        "fields": fields
                    }
                )
                
                update_data = update_response.json()
                if 'error' in update_data:
                    return JsonResponse({'error': f'Ошибка обновления: {update_data["error"]}'}, status=500)
            
            return JsonResponse({
                'success': True,
                'doc_type': doc_type,
                'deal_id': deal_id,
                'document': {
                    'name': original_name,
                    'uploaded_at': datetime.now().strftime('%d.%m.%Y %H:%M')
                }
            })
        
        # =============================================
        # ДЛЯ ПРАВ — ОБЫЧНАЯ ЗАГРУЗКА
        # =============================================
        search_response = requests.post(
            webhook + "crm.item.list",
            json={
                "entityTypeId": entity_type_id,
                "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
            }
        )
        
        search_data = search_response.json()
        
        if 'error' in search_data:
            return JsonResponse({'error': f'Ошибка поиска: {search_data["error"]}'}, status=500)
        
        items = search_data.get('result', {}).get('items', [])
        
        if not items:
            return JsonResponse({'error': 'Элемент с таким РФС ID не найден'}, status=404)
        
        item_id = items[0]['id']
        
        fields = {
            bitrix_field: [upload_name, file_base64]
        }
        
        update_response = requests.post(
            webhook + "crm.item.update",
            json={
                "entityTypeId": entity_type_id,
                "id": item_id,
                "fields": fields
            }
        )
        
        update_data = update_response.json()
        
        if 'error' in update_data:
            return JsonResponse({'error': f'Ошибка загрузки в Битрикс24: {update_data["error"]}'}, status=500)
        
        response_data = {
            'success': True,
            'doc_type': doc_type,
            'document': {
                'name': original_name,
                'uploaded_at': datetime.now().strftime('%d.%m.%Y %H:%M')
            }
        }
        
        if upload_name != original_name:
            response_data['warning'] = f'Имя файла в системе изменено на: {upload_name}'
        
        return JsonResponse(response_data)
        
    except Club.DoesNotExist:
        return JsonResponse({'error': 'Клуб не найден'}, status=404)
    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

# =====================================================
# УДАЛЕНИЕ ДОКУМЕНТА
# =====================================================

@csrf_exempt
@login_required
def delete_club_document(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    try:
        data = json.loads(request.body)
        doc_type = data.get('doc_type', 'rights')
        bitrix_field = get_bitrix_field(doc_type)
        
        club = Club.objects.filter(user=request.user).first()
        if not club:
            return JsonResponse({'error': 'Клуб не найден'}, status=404)
        
        if not club.rfs_id:
            return JsonResponse({'error': 'У клуба не указан РФС ID'}, status=400)
        
        webhook = settings.BITRIX24_WEBHOOK
        entity_type_id = settings.SMART_PROCESS_ID
        
        search_response = requests.post(
            webhook + "crm.item.list",
            json={
                "entityTypeId": entity_type_id,
                "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
            }
        )
        
        search_data = search_response.json()
        items = search_data.get('result', {}).get('items', [])
        
        if not items:
            return JsonResponse({'error': 'Элемент не найден'}, status=404)
        
        item_id = items[0]['id']
        
        fields = {
            bitrix_field: 0
        }
        
        if doc_type == 'umo':
            fields['ufCrm8_1782815972'] = 'N'
        elif doc_type == 'insurance':
            fields['ufCrm8_1782815987'] = 'N'
        
        update_response = requests.post(
            webhook + "crm.item.update",
            json={
                "entityTypeId": entity_type_id,
                "id": item_id,
                "fields": fields
            }
        )
        
        update_data = update_response.json()
        
        if 'error' in update_data:
            return JsonResponse({'error': f'Ошибка удаления: {update_data["error"]}'}, status=500)
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================================================
# === АДМИН-ПАНЕЛЬ ДЛЯ ВЕРИФИКАЦИИ
# =====================================================

@staff_member_required
def admin_verify_documents(request):
    """Страница для верификации документов клубов"""
    clubs = Club.objects.all().order_by('sport_name')
    
    clubs_data = []
    webhook = settings.BITRIX24_WEBHOOK
    entity_type_id = settings.SMART_PROCESS_ID
    
    for club in clubs:
        if not club.rfs_id:
            clubs_data.append({
                'club': club,
                'has_rights': False,
                'has_umo': False,
                'has_insurance': False,
                'umo_verified': False,
                'insurance_verified': False,
                'rights_verified': False,
                'rights_file_name': None,
                'umo_file_name': None,
                'insurance_file_name': None,
                'error': 'Нет РФС ID'
            })
            continue
        
        try:
            search_response = requests.post(
                webhook + "crm.item.list",
                json={
                    "entityTypeId": entity_type_id,
                    "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
                }
            )
            search_data = search_response.json()
            items = search_data.get('result', {}).get('items', [])
            
            if items:
                item = items[0]
                
                def has_file(field_value):
                    if not field_value or field_value == 0:
                        return False
                    if isinstance(field_value, dict):
                        return bool(field_value.get('id') or field_value.get('urlMachine'))
                    if isinstance(field_value, list) and len(field_value) > 0:
                        return True
                    if isinstance(field_value, str) and field_value:
                        return True
                    return False
                
                def get_file_name(field_value):
                    if not field_value or field_value == 0:
                        return None
                    if isinstance(field_value, dict):
                        download_url = field_value.get('urlMachine') or field_value.get('url') or None
                        if download_url:
                            return get_file_name_from_url(download_url)
                    return None
                
                clubs_data.append({
                    'club': club,
                    'has_rights': has_file(item.get('ufCrm8_1782371217')),
                    'has_umo': has_file(item.get('ufCrm8_1782742262')),
                    'has_insurance': has_file(item.get('ufCrm8_1782742287')),
                    'umo_verified': item.get('ufCrm8_1782815972') == 'Y',
                    'insurance_verified': item.get('ufCrm8_1782815987') == 'Y',
                    'rights_verified': item.get('ufCrm8_1782382317') == 'Y',
                    'rights_file_name': get_file_name(item.get('ufCrm8_1782371217')),
                    'umo_file_name': get_file_name(item.get('ufCrm8_1782742262')),
                    'insurance_file_name': get_file_name(item.get('ufCrm8_1782742287')),
                })
            else:
                clubs_data.append({
                    'club': club,
                    'has_rights': False,
                    'has_umo': False,
                    'has_insurance': False,
                    'umo_verified': False,
                    'insurance_verified': False,
                    'rights_verified': False,
                    'rights_file_name': None,
                    'umo_file_name': None,
                    'insurance_file_name': None,
                    'error': 'Элемент не найден'
                })
        except Exception as e:
            clubs_data.append({
                'club': club,
                'has_rights': False,
                'has_umo': False,
                'has_insurance': False,
                'umo_verified': False,
                'insurance_verified': False,
                'rights_verified': False,
                'rights_file_name': None,
                'umo_file_name': None,
                'insurance_file_name': None,
                'error': str(e)
            })
    
    return render(request, 'clubs/admin_verify.html', {'clubs_data': clubs_data})


@staff_member_required
@csrf_exempt
def admin_verify_action(request):
    """API для верификации документа"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    try:
        data = json.loads(request.body)
        club_id = data.get('club_id')
        doc_type = data.get('doc_type')
        action = data.get('action')
        
        if not club_id or not doc_type:
            return JsonResponse({'error': 'Не все параметры переданы'}, status=400)
        
        club = Club.objects.get(id=club_id)
        
        if not club.rfs_id:
            return JsonResponse({'error': 'У клуба не указан РФС ID'}, status=400)
        
        webhook = settings.BITRIX24_WEBHOOK
        entity_type_id = settings.SMART_PROCESS_ID
        
        VERIFY_FIELDS = {
            'umo': 'ufCrm8_1782815972',
            'insurance': 'ufCrm8_1782815987',
            'rights': 'ufCrm8_1782382317',
        }
        
        bitrix_field = VERIFY_FIELDS.get(doc_type)
        if not bitrix_field:
            return JsonResponse({'error': 'Неизвестный тип документа'}, status=400)
        
        search_response = requests.post(
            webhook + "crm.item.list",
            json={
                "entityTypeId": entity_type_id,
                "filter": {"ufCrm8_1782372679": str(club.rfs_id)}
            }
        )
        
        search_data = search_response.json()
        items = search_data.get('result', {}).get('items', [])
        
        if not items:
            return JsonResponse({'error': 'Элемент не найден'}, status=404)
        
        item_id = items[0]['id']
        
        value = 'Y'
        
        update_response = requests.post(
            webhook + "crm.item.update",
            json={
                "entityTypeId": entity_type_id,
                "id": item_id,
                "fields": {
                    bitrix_field: value
                }
            }
        )
        
        update_data = update_response.json()
        
        if 'error' in update_data:
            return JsonResponse({'error': update_data['error']}, status=500)
        
        return JsonResponse({
            'success': True,
            'club_id': club_id,
            'doc_type': doc_type,
            'verified': value == 'Y'
        })
        
    except Club.DoesNotExist:
        return JsonResponse({'error': 'Клуб не найден'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)