from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, HttpResponse
from .models import Photo
from .forms import ICloudLoginForm, PhotoUploadForm
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException, PyiCloudServiceNotActivatedException
from django.core.files.base import ContentFile
from django.contrib.auth import login, authenticate
from PIL import Image
from pillow_heif import register_heif_opener
import os
import io
import logging
import mimetypes
import time
import requests
from requests.exceptions import ChunkedEncodingError
from moviepy import VideoFileClip
import tempfile
from .forms import SignUpForm

logger = logging.getLogger(__name__)

register_heif_opener()

def sign_up(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Hesabınız oluşturuldu, {user.username}!")
            logger.debug(f"New user registered: {user.username}")
            return redirect('photo_list')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = SignUpForm()
    return render(request, 'photos/sign_up.html', {'form': form})

@login_required
def photo_list(request):
    photos = Photo.objects.filter(user=request.user)
    return render(request, 'photos/photo_list.html', {'photos': photos})

@login_required
def icloud_login(request):
    if request.method == 'POST':
        form = ICloudLoginForm(request.POST)
        if form.is_valid():
            apple_id = form.cleaned_data['apple_id']
            password = form.cleaned_data['password']
            request.session['icloud_credentials'] = {'apple_id': apple_id, 'password': password}
            return redirect('photos:icloud_select_photos') 
    else:
        form = ICloudLoginForm()
    return render(request, 'photos/icloud_login.html', {'form': form})

@login_required
def icloud_2fa(request):
    if 'icloud_credentials' not in request.session:
        messages.error(request, "Lütfen iCloud hesabınızla giriş yapın.")
        return redirect('icloud_login')
    
    apple_id = request.session['icloud_credentials']['apple_id']
    password = request.session['icloud_credentials']['password']
    
    try:
        api = PyiCloudService(apple_id, password)
        if not (api.requires_2fa or api.requires_2sa):
            return redirect('icloud_select_photos')
        
        if request.method == 'POST':
            code = request.POST.get('code')
            if code:
                try:
                    if api.requires_2fa:
                        result = api.validate_2fa_code(code)
                    else:
                        result = api.validate_verification_code(None, code)
                    if result:
                        request.session['2fa_code'] = code
                        messages.success(request, "2FA doğrulama başarılı.")
                        return redirect('icloud_select_photos')
                    else:
                        messages.error(request, "Geçersiz doğrulama kodu. Lütfen tekrar deneyin.")
                except Exception as e:
                    messages.error(request, f"Doğrulama hatası: {str(e)}")
                    logger.error(f"2FA verification error: {str(e)}")
            else:
                messages.error(request, "Lütfen doğrulama kodunu girin.")
        
        if api.requires_2fa:
            api.send_verification_code()
            messages.info(request, "Doğrulama kodu Apple cihazlarınıza gönderildi.")
        return render(request, 'photos/icloud_2fa.html')
    
    except PyiCloudFailedLoginException as e:
        messages.error(request, f"iCloud giriş bilgileri hatalı: {str(e)}. Lütfen tekrar deneyin.")
        del request.session['icloud_credentials']
        logger.error(f"iCloud login failed: {str(e)}")
        return redirect('icloud_login')
    except Exception as e:
        messages.error(request, f"Bir hata oluştu: {str(e)}. Lütfen tekrar deneyin.")
        del request.session['icloud_credentials']
        logger.error(f"Unexpected error: {type(e).__name__}: {str(e)}")
        return redirect('icloud_login')

@login_required
def icloud_select_photos(request):
    if 'icloud_credentials' not in request.session:
        messages.error(request, "Lütfen iCloud hesabınızla giriş yapın.")
        return redirect('icloud_login')
    
    apple_id = request.session['icloud_credentials']['apple_id']
    password = request.session['icloud_credentials']['password']
    
    max_retries = 3
    retry_delay = 5  # seconds
    photos_per_page = 20  # Media items per page
    download_retries = 2  # Retry attempts for thumbnail downloads
    
    page = int(request.GET.get('page', 1))
    start_index = (page - 1) * photos_per_page
    end_index = start_index + photos_per_page
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"iCloud bağlantısı deneniyor (Deneme {attempt + 1}/{max_retries})...")
            api = PyiCloudService(apple_id, password)
            logger.debug(f"Bağlantı başarılı. 2FA Gerekli: {api.requires_2fa}, 2SA Gerekli: {api.requires_2sa}")
            
            if api.requires_2fa or api.requires_2sa:
                return redirect('icloud_2fa')
            
            logger.debug("Medya dosyaları alınıyor...")
            photos = list(api.photos.all)[start_index:end_index]
            total_photos = len(api.photos.all)
            logger.debug(f"{len(photos)} medya alındı (Sayfa {page}).")
            
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
                                logger.warning(f"Failed to download {photo.filename}: Status {response.status_code if response else 'No response'}")
                        except (ChunkedEncodingError, ConnectionError) as e:
                            messages.warning(request, f"{photo.filename} indirilirken bağlantı hatası: {str(e)}")
                            logger.error(f"Connection error downloading {photo.filename}: {str(e)}")
                messages.success(request, "Seçilen medya dosyaları eklendi.")
                del request.session['icloud_credentials']
                if '2fa_code' in request.session:
                    del request.session['2fa_code']
                return redirect('photo_list')
            
            photo_list = []
            media_dir = os.path.join('media', 'thumbnails')
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
                    logger.debug(f"Using existing thumbnail for {photo.filename}: {thumb_path}")
                else:
                    for dl_attempt in range(download_retries):
                        try:
                            if is_video:
                                # Download video to a temporary file
                                response = photo.download('original')
                                if not response or response.status_code != 200:
                                    logger.warning(f"Video download failed for {photo.filename}: Status {response.status_code if response else 'No response'}")
                                    if dl_attempt < download_retries - 1:
                                        time.sleep(retry_delay)
                                        continue
                                    else:
                                        raise ValueError("Video download failed after retries")
                                
                                # Save video to temporary file
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
                                    temp_file.write(response.content)
                                    temp_file_path = temp_file.name
                                
                                # Generate thumbnail from video
                                clip = VideoFileClip(temp_file_path)
                                frame_time = min(1.0, clip.duration / 2)  # Take frame at 1s or midpoint
                                frame = clip.get_frame(frame_time)
                                clip.close()
                                
                                # Convert frame to PIL Image
                                img = Image.fromarray(frame)
                                img.thumbnail((100, 100), Image.Resampling.LANCZOS)
                                thumb_io = io.BytesIO()
                                img.save(thumb_io, format='JPEG', quality=70)
                                thumb_io.seek(0)
                                
                                # Save thumbnail
                                with open(thumb_path, 'wb') as f:
                                    f.write(thumb_io.getvalue())
                                photo_data['thumbnail'] = f"/{thumb_path}"
                                logger.debug(f"Generated video thumbnail for {photo.filename}: {thumb_path}")
                                
                                # Clean up
                                os.unlink(temp_file_path)
                                break
                            else:
                                # Download thumbnail for PNG/HEIC
                                response = photo.download('thumb')
                                if not response or response.status_code != 200:
                                    logger.warning(f"Thumbnail download failed for {photo.filename}: Status {response.status_code if response else 'No response'}")
                                    if dl_attempt < download_retries - 1:
                                        time.sleep(retry_delay)
                                        continue
                                    else:
                                        raise ValueError("Thumbnail download failed after retries")
                                
                                # Process image
                                img_data = response.content
                                img = Image.open(io.BytesIO(img_data))
                                img.verify()  # Verify image integrity
                                img = Image.open(io.BytesIO(img_data))  # Re-open after verify
                                
                                # Handle various image modes
                                if img.mode not in ('RGB', 'L'):
                                    logger.debug(f"Converting image mode for {photo.filename}: {img.mode} to RGB")
                                    img = img.convert('RGB')
                                
                                # Generate thumbnail
                                img.thumbnail((100, 100), Image.Resampling.LANCZOS)
                                thumb_io = io.BytesIO()
                                img.save(thumb_io, format='JPEG', quality=70)
                                thumb_io.seek(0)
                                
                                # Save thumbnail to disk
                                with open(thumb_path, 'wb') as f:
                                    f.write(thumb_io.getvalue())
                                photo_data['thumbnail'] = f"/{thumb_path}"
                                logger.debug(f"Generated thumbnail for {photo.filename}: {thumb_path}")
                                break
                        
                        except (ChunkedEncodingError, ConnectionError) as e:
                            logger.error(f"Connection error for {photo.filename} (Attempt {dl_attempt + 1}/{download_retries}): {str(e)}")
                            if dl_attempt < download_retries - 1:
                                time.sleep(retry_delay)
                                continue
                            photo_data['thumbnail'] = '/media/placeholder.jpg'
                            logger.warning(f"Using placeholder for {photo.filename} due to connection error")
                        
                        except Image.UnidentifiedImageError as e:
                            logger.error(f"Image format error for {photo.filename}: {str(e)}")
                            photo_data['thumbnail'] = '/media/placeholder.jpg'
                            logger.warning(f"Using placeholder for {photo.filename} due to invalid image format")
                            break
                        
                        except Exception as e:
                            logger.error(f"Unexpected error for {photo.filename}: {type(e).__name__}: {str(e)}")
                            photo_data['thumbnail'] = '/media/placeholder.jpg'
                            logger.warning(f"Using placeholder for {photo.filename} due to unexpected error")
                            break
                
                if not photo_data['thumbnail']:
                    photo_data['thumbnail'] = '/media/placeholder.jpg'
                    messages.warning(request, f"{photo.filename} için thumbnail oluşturulamadı.")
                    logger.warning(f"Using placeholder for {photo.filename} due to thumbnail generation failure")
                
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
                    logger.debug(f"503 Hatası alındı, {retry_delay} saniye sonra tekrar denenecek...")
                    time.sleep(retry_delay)
                    continue
                else:
                    messages.error(request, "iCloud servisi şu anda kullanılamıyor (503). Lütfen daha sonra tekrar deneyin.")
                    del request.session['icloud_credentials']
                    logger.error("iCloud service unavailable (503) after retries")
                    return redirect('icloud_login')
            else:
                messages.error(request, f"iCloud bağlantı hatası: {str(e)}. Lütfen tekrar deneyin.")
                del request.session['icloud_credentials']
                logger.error(f"iCloud connection error: {str(e)}")
                return redirect('icloud_login')
        except PyiCloudFailedLoginException as e:
            messages.error(request, f"iCloud giriş bilgileri hatalı: {str(e)}. Lütfen tekrar deneyin.")
            del request.session['icloud_credentials']
            logger.error(f"iCloud login failed: {str(e)}")
            return redirect('icloud_login')
        except PyiCloudServiceNotActivatedException as e:
            messages.error(request, f"iCloud servisi aktif değil: {str(e)}. Lütfen https://icloud.com/ üzerinden oturum açarak servisi etkinleştirin.")
            del request.session['icloud_credentials']
            logger.error(f"iCloud service not activated: {str(e)}")
            return redirect('icloud_login')
        except Exception as e:
            messages.error(request, f"Bir hata oluştu: {str(e)}. Lütfen tekrar deneyin.")
            del request.session['icloud_credentials']
            logger.error(f"Unexpected error: {type(e).__name__}: {str(e)}")
            return redirect('icloud_login')
    
    messages.error(request, "iCloud servisine bağlanılamadı. Lütfen daha sonra tekrar deneyin.")
    del request.session['icloud_credentials']
    logger.error("Failed to connect to iCloud after retries")
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
            photos = Photo.objects.filter(id__in=photo_ids, user=request.user)
            for photo in photos:
                if os.path.exists(photo.image.path):
                    os.remove(photo.image.path)
                photo.delete()
            messages.success(request, f"{len(photos)} fotoğraf silindi.")
        else:
            messages.warning(request, "Lütfen silmek için en az bir fotoğraf seçin.")
    return redirect('photo_list')

@login_required
def delete_all_photos(request):
    if request.method == 'POST':
        photos = Photo.objects.filter(user=request.user)
        for photo in photos:
            if os.path.exists(photo.image.path):
                os.remove(photo.image.path)
            photo.delete()
        messages.success(request, "Tüm fotoğraflar silindi.")
    return redirect('photo_list')

@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        photos = Photo.objects.filter(user=user)
        for photo in photos:
            if os.path.exists(photo.image.path):
                os.remove(photo.image.path)
            photo.delete()
        user.delete()
        messages.success(request, "Hesabınız ve tüm fotoğraflarınız silindi.")
        return redirect('photo_list')
    return render(request, 'photos/confirm_delete_account.html')

@login_required
def download_photo(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id, user=request.user)
    file_path = photo.image.path
    
    if not os.path.exists(file_path):
        logger.error(f"File not found for download: {file_path}")
        messages.error(request, f"Dosya bulunamadı: {photo.image.name}")
        return redirect('photo_list')
    
    try:
        file_handle = open(file_path, 'rb')
        response = FileResponse(file_handle, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        logger.debug(f"Downloading file: {file_path} for user: {request.user.username}")
        return response
    except Exception as e:
        logger.error(f"Error downloading file {file_path}: {str(e)}")
        messages.error(request, f"Dosya indirilemedi: {str(e)}")
        if 'file_handle' in locals():
            file_handle.close()
        return redirect('photo_list')
    
@login_required
def play_video(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id, user=request.user)
    if not photo.is_video:
        messages.error(request, "Bu dosya bir video değil.")
        return redirect('photos:photo_list')
    return render(request, 'photos/play_video.html', {'photo': photo})