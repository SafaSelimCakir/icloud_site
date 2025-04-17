from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from pyicloud import PyiCloudService
from .forms import ICloudLoginForm, PhotoUploadForm
from .models import Photo
from django.core.files.base import ContentFile
from django.contrib import messages
from PIL import Image
import io
import os
from requests.exceptions import ChunkedEncodingError, ConnectionError
from django.contrib.auth import logout
from pyicloud.exceptions import PyiCloudFailedLoginException, PyiCloudServiceNotActivatedException
import time
import requests
from pillow_heif import register_heif_opener
from moviepy.editor import VideoFileClip
import mimetypes

# HEIC formatı desteği
register_heif_opener()

@login_required
def photo_list(request):
    photos = Photo.objects.filter(user=request.user)
    return render(request, 'photos/photo_list.html', {'photos': photos})

@login_required
def icloud_login(request):
    if request.method == 'POST':
        form = ICloudLoginForm(request.POST)
        if form.is_valid():
            request.session['icloud_credentials'] = {
                'apple_id': form.cleaned_data['apple_id'],
                'password': form.cleaned_data['password']
            }
            return redirect('icloud_select_photos')
    else:
        form = ICloudLoginForm()
    return render(request, 'photos/icloud_login.html', {'form': form})

egister_heif_opener()

@login_required
def icloud_select_photos(request):
    if 'icloud_credentials' not in request.session:
        messages.error(request, "Lütfen iCloud hesabınızla giriş yapın.")
        return redirect('icloud_login')
    
    apple_id = request.session['icloud_credentials']['apple_id']
    password = request.session['icloud_credentials']['password']
    
    max_retries = 3
    retry_delay = 5  # saniye
    photos_per_page = 20  # Her sayfada gösterilecek medya sayısı
    
    page = int(request.GET.get('page', 1))
    start_index = (page - 1) * photos_per_page
    end_index = start_index + photos_per_page
    
    for attempt in range(max_retries):
        try:
            print(f"iCloud bağlantısı deneniyor (Deneme {attempt + 1}/{max_retries})...")
            api = PyiCloudService(apple_id, password)
            print(f"Bağlantı başarılı. 2FA Gerekli: {api.requires_2fa}, 2SA Gerekli: {api.requires_2sa}")
            
            if api.requires_2fa or api.requires_2sa:
                return redirect('icloud_2fa')
            
            print("Medya dosyaları alınıyor...")
            photos = list(api.photos.all)[start_index:end_index]
            total_photos = len(api.photos.all)
            print(f"{len(photos)} medya alındı (Sayfa {page}).")
            
            if request.method == 'POST' and 'photo_ids' in request.POST:
                selected_photo_ids = request.POST.getlist('photo_ids')
                for photo in api.photos.all:
                    if photo.id in selected_photo_ids:
                        try:
                            response = photo.download('original')
                            if response and response.status_code == 200:
                                photo_data = response.content
                                photo_instance = Photo(user=request.user)
                                photo_instance.image.save(photo.filename, ContentFile(photo_data))
                                photo_instance.save()
                            else:
                                messages.warning(request, f"{photo.filename} indirilemedi.")
                        except (ChunkedEncodingError, ConnectionError) as e:
                            messages.warning(request, f"{photo.filename} indirilirken bağlantı hatası: {str(e)}")
                messages.success(request, "Seçilen medya dosyaları eklendi.")
                del request.session['icloud_credentials']
                if '2fa_code' in request.session:
                    del request.session['2fa_code']
                return redirect('photo_list')
            
            photo_list = []
            media_dir = 'media/thumbnails'
            os.makedirs(media_dir, exist_ok=True)
            
            for photo in photos:
                photo_data = {
                    'id': photo.id,
                    'filename': photo.filename,
                    'size': photo.size,
                    'thumbnail': None,
                    'is_video': False
                }
                
                mime_type, _ = mimetypes.guess_type(photo.filename)
                is_video = mime_type and mime_type.startswith('video')
                photo_data['is_video'] = is_video
                
                thumb_name = f"thumb_{photo.id}.jpg"
                thumb_path = os.path.join(media_dir, thumb_name)
                
                if os.path.exists(thumb_path):
                    photo_data['thumbnail'] = f"/{thumb_path}"
                else:
                    try:
                        if is_video:
                            response = photo.download('original')
                            if response and response.status_code == 200:
                                temp_video_path = os.path.join(media_dir, f"temp_{photo.id}{os.path.splitext(photo.filename)[1]}")
                                with open(temp_video_path, 'wb') as f:
                                    f.write(response.content)
                                
                                clip = VideoFileClip(temp_video_path)
                                frame = clip.get_frame(1)
                                clip.close()
                                
                                img = Image.fromarray(frame)
                                img.thumbnail((100, 100))
                                if img.mode in ('RGBA', 'P', 'LA'):
                                    img = img.convert('RGB')
                                thumb_io = io.BytesIO()
                                img.save(thumb_io, format='JPEG', quality=70)
                                thumb_io.seek(0)
                                with open(thumb_path, 'wb') as f:
                                    f.write(thumb_io.getvalue())
                                photo_data['thumbnail'] = f"/{thumb_path}"
                                
                                os.remove(temp_video_path)
                            else:
                                print(f"Video indirilemedi: {photo.filename}")
                        else:
                            response = photo.download('thumb')
                            if response and response.status_code == 200:
                                img = Image.open(io.BytesIO(response.content))
                                img.verify()
                                img = Image.open(io.BytesIO(response.content))
                                img.thumbnail((100, 100))
                                if img.mode in ('RGBA', 'P', 'LA'):
                                    img = img.convert('RGB')
                                thumb_io = io.BytesIO()
                                img.save(thumb_io, format='JPEG', quality=70)
                                thumb_io.seek(0)
                                with open(thumb_path, 'wb') as f:
                                    f.write(thumb_io.getvalue())
                                photo_data['thumbnail'] = f"/{thumb_path}"
                            else:
                                print(f"Thumbnail indirilemedi: {photo.filename}")
                    except (ChunkedEncodingError, ConnectionError, Image.UnidentifiedImageError, ValueError, OSError) as e:
                        print(f"Hata: {photo.filename} ({'Video' if is_video else 'Fotoğraf'}) - {str(e)}")
                
                if not photo_data['thumbnail']:
                    photo_data['thumbnail'] = '/media/placeholder.jpg'
                    messages.warning(request, f"{photo.filename} için thumbnail oluşturulamadı.")
                
                photo_list.append(photo_data)
            
            context = {
                'photos': photo_list,
                'current_page': page,
                'total_pages': (total_photos + photos_per_page - 1) // photos_per_page,
                'total_photos': total_photos
            }
            return render(request, 'photos/icloud_select.html', context)
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:
                if attempt < max_retries - 1:
                    print(f"503 Hatası alındı, {retry_delay} saniye sonra tekrar denenecek...")
                    time.sleep(retry_delay)
                    continue
                else:
                    messages.error(request, "iCloud servisi şu anda kullanılamıyor (503). Lütfen daha sonra tekrar deneyin.")
                    del request.session['icloud_credentials']
                    return redirect('icloud_login')
            else:
                messages.error(request, f"iCloud bağlantı hatası: {str(e)}. Lütfen tekrar deneyin.")
                del request.session['icloud_credentials']
                return redirect('icloud_login')
        except PyiCloudFailedLoginException as e:
            messages.error(request, f"iCloud giriş bilgileri hatalı: {str(e)}. Lütfen tekrar deneyin.")
            del request.session['icloud_credentials']
            return redirect('icloud_login')
        except PyiCloudServiceNotActivatedException as e:
            messages.error(request, f"iCloud servisi aktif değil: {str(e)}. Lütfen https://icloud.com/ üzerinden oturum açarak servisi etkinleştirin.")
            del request.session['icloud_credentials']
            return redirect('icloud_login')
        except Exception as e:
            messages.error(request, f"Bir hata oluştu: {str(e)}. Lütfen tekrar deneyin.")
            del request.session['icloud_credentials']
            return redirect('icloud_login')
    
    messages.error(request, "iCloud servisine bağlanılamadı. Lütfen daha sonra tekrar deneyin.")
    del request.session['icloud_credentials']
    return redirect('icloud_login')

@login_required
def icloud_2fa(request):
    if 'icloud_credentials' not in request.session:
        messages.error(request, "Lütfen iCloud hesabınızla giriş yapın.")
        return redirect('icloud_login')
    
    apple_id = request.session['icloud_credentials']['apple_id']
    password = request.session['icloud_credentials']['password']
    
    try:
        api = PyiCloudService(apple_id, password)
        print(f"Apple ID: {apple_id}, 2FA Gerekli: {api.requires_2fa}, 2SA Gerekli: {api.requires_2sa}")
        
        if not (api.requires_2fa or api.requires_2sa):
            return redirect('icloud_select_photos')
        
        if request.method == 'POST' and '2fa_code' in request.POST:
            code = request.POST.get('2fa_code').strip()
            try:
                if api.validate_2fa_code(code):
                    request.session['2fa_code'] = code
                    messages.success(request, "2FA doğrulama başarılı.")
                    return redirect('icloud_select_photos')
                else:
                    messages.error(request, "Geçersiz 2FA kodu. Lütfen tekrar deneyin.")
            except Exception as e:
                messages.error(request, f"2FA kodu doğrulama hatası: {str(e)}")
        else:
            trusted_devices = api.trusted_devices
            print(f"Güvenilir Cihazlar: {trusted_devices}")
            if not trusted_devices:
                messages.warning(request, "Güvenilir cihaz bulunamadı, ancak doğrulama kodu gönderilmiş olabilir. Lütfen cihazınıza gelen kodu girin.")
            else:
                device = trusted_devices[0]
                try:
                    api.send_verification_code(device)
                    messages.info(request, f"Doğrulama kodu {device.get('deviceName', 'cihazınıza')} gönderildi.")
                except Exception as e:
                    messages.error(request, f"Doğrulama kodu gönderilemedi: {str(e)}")
                    messages.warning(request, "Kod gönderilemedi, ancak cihazınıza gelen bir kodu girebilirsiniz.")
        
        return render(request, 'photos/icloud_2fa.html', {})
    
    except PyiCloudFailedLoginException as e:
        messages.error(request, f"iCloud giriş bilgileri hatalı: {str(e)}. Lütfen tekrar deneyin.")
        del request.session['icloud_credentials']
        return redirect('icloud_login')
    except PyiCloudServiceNotActivatedException as e:
        messages.error(request, f"iCloud servisi aktif değil: {str(e)}. Lütfen https://icloud.com/ üzerinden oturum açarak servisi etkinleştirin.")
        del request.session['icloud_credentials']
        return redirect('icloud_login')
    except Exception as e:
        messages.error(request, f"Bir hata oluştu: {str(e)}. Lütfen tekrar deneyin.")
        del request.session['icloud_credentials']
        return redirect('icloud_login')

@login_required
def upload_photo(request):
    if request.method == 'POST':
        form = PhotoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.user = request.user
            photo.save()
            messages.success(request, "Fotoğraf başarıyla yüklendi.")
            return redirect('photo_list')
    else:
        form = PhotoUploadForm()
    return render(request, 'photos/upload_photo.html', {'form': form})

@login_required
def delete_photos(request):
    if request.method == 'POST':
        photo_ids = request.POST.getlist('photo_ids')
        if photo_ids:
            Photo.objects.filter(id__in=photo_ids, user=request.user).delete()
            messages.success(request, "Seçilen fotoğraflar silindi.")
        else:
            messages.warning(request, "Silmek için fotoğraf seçmediniz.")
        return redirect('photo_list')
    return redirect('photo_list')

@login_required
def delete_all_photos(request):
    if request.method == 'POST' or request.method == 'GET':
        Photo.objects.filter(user=request.user).delete()
        messages.success(request, "Tüm fotoğraflar silindi.")
        return redirect('photo_list')
    return redirect('photo_list')

@login_required
def delete_account(request):
    if request.method == 'POST':
        Photo.objects.filter(user=request.user).delete()
        user = request.user
        logout(request)
        user.delete()
        messages.success(request, "Hesabınız başarıyla silindi.")
        return redirect('photo_list')
    return render(request, 'photos/confirm_delete_account.html', {})