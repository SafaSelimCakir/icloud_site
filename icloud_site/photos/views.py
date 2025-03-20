from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from pyicloud import PyiCloudService
from .forms import ICloudLoginForm, PhotoForm
from .models import Photo
from django.core.files.base import ContentFile
from django.contrib import messages
from PIL import Image
import io
import os
from django.core.paginator import Paginator
from requests.exceptions import ChunkedEncodingError, ConnectionError
import ffmpeg

@login_required
def icloud_login(request):
    if request.method == 'POST':
        form = ICloudLoginForm(request.POST)
        if form.is_valid():
            apple_id = form.cleaned_data['apple_id']
            password = form.cleaned_data['password']
            try:
                api = PyiCloudService(apple_id, password)
                if api.requires_2fa:
                    request.session['icloud_credentials'] = {'apple_id': apple_id, 'password': password}
                    return redirect('icloud_2fa')
                request.session['icloud_credentials'] = {'apple_id': apple_id, 'password': password}
                return redirect('icloud_select_photos')
            except Exception as e:
                messages.error(request, f"iCloud bağlantısı başarısız: {str(e)}")
                return render(request, 'photos/icloud_login.html', {'form': form})
    else:
        form = ICloudLoginForm()
    return render(request, 'photos/icloud_login.html', {'form': form})

@login_required
def icloud_2fa(request):
    if 'icloud_credentials' not in request.session:
        return redirect('icloud_login')
    
    if request.method == 'POST':
        code = request.POST.get('code')
        apple_id = request.session['icloud_credentials']['apple_id']
        password = request.session['icloud_credentials']['password']
        
        try:
            api = PyiCloudService(apple_id, password)
            if api.validate_2fa_code(code):
                return redirect('icloud_select_photos')
            else:
                return render(request, 'photos/icloud_2fa.html', {'error': 'Geçersiz doğrulama kodu'})
        except Exception as e:
            return render(request, 'photos/icloud_2fa.html', {'error': str(e)})
    
    return render(request, 'photos/icloud_2fa.html')

@login_required
def icloud_select_photos(request):
    if 'icloud_credentials' not in request.session:
        return redirect('icloud_login')
    
    apple_id = request.session['icloud_credentials']['apple_id']
    password = request.session['icloud_credentials']['password']
    api = PyiCloudService(apple_id, password)
    photos = api.photos.all
    
    if request.method == 'POST':
        selected_photo_ids = request.POST.getlist('photo_ids')
        for photo in photos:
            if photo.id in selected_photo_ids:
                try:
                    response = photo.download()
                    if response and response.status_code == 200:
                        photo_data = response.content
                        photo_instance = Photo(user=request.user)
                        photo_instance.image.save(photo.filename, ContentFile(photo_data))
                        photo_instance.save()
                    else:
                        messages.warning(request, f"{photo.filename} indirilemedi.")
                except (ChunkedEncodingError, ConnectionError) as e:
                    messages.warning(request, f"{photo.filename} indirilirken bağlantı hatası: {str(e)}")
        messages.success(request, "Seçilen fotoğraflar eklendi.")
        del request.session['icloud_credentials']
        return redirect('photo_list')
    
    filter_type = request.GET.get('filter', 'all') 
    
    thumbnail_dir = os.path.join('media', 'thumbnails')
    os.makedirs(thumbnail_dir, exist_ok=True)
    
    photo_list = [{'id': photo.id, 'filename': photo.filename, 'size': photo.size} for photo in photos]
    
    if filter_type == 'images':
        photo_list = [photo for photo in photo_list if photo['filename'].lower().endswith(('.jpg', '.jpeg', '.png', '.heic'))]
    elif filter_type == 'videos':
        photo_list = [photo for photo in photo_list if photo['filename'].lower().endswith(('.mov', '.mp4', '.avi'))]
    
    paginator = Paginator(photo_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    for photo_data in page_obj.object_list:
        thumb_name = f"thumb_{photo_data['filename']}"
        thumb_path = os.path.join(thumbnail_dir, thumb_name)
        
        if os.path.exists(thumb_path):
            photo_data['thumbnail'] = f"/media/thumbnails/{thumb_name}"
        else:
            for photo in photos:
                if photo.id == photo_data['id']:
                    try:
                        response = photo.download()
                        if response and response.status_code == 200:
                            if photo_data['filename'].lower().endswith(('.mov', '.mp4', '.avi')):
                                photo_data['thumbnail'] = None 
                            else:
                                img = Image.open(io.BytesIO(response.content))
                                img.verify()
                                img = Image.open(io.BytesIO(response.content))
                                img.thumbnail((100, 100))
                                if img.mode in ('RGBA', 'P', 'LA'):
                                    img = img.convert('RGB')
                                thumb_io = io.BytesIO()
                                img.save(thumb_io, format='JPEG')
                                thumb_io.seek(0)
                                with open(thumb_path, 'wb') as f:
                                    f.write(thumb_io.getvalue())
                                photo_data['thumbnail'] = f"/media/thumbnails/{thumb_name}"
                        else:
                            photo_data['thumbnail'] = None
                    except (ChunkedEncodingError, ConnectionError) as e:
                        print(f"Bağlantı hatası: {photo.filename} - {str(e)}")
                        photo_data['thumbnail'] = None
                    except (Image.UnidentifiedImageError, ValueError, OSError) as e:
                        print(f"Resim hatası: {photo.filename} - {str(e)}")
                        photo_data['thumbnail'] = None
                    break
    
    context = {
        'page_obj': page_obj,
        'current_filter': filter_type,
    }
    return render(request, 'photos/icloud_select.html', context)

@login_required
def photo_list(request):
    # Filtreleme parametresini al
    filter_type = request.GET.get('filter', 'all')  # Varsayılan: hepsi
    
    # Kullanıcının tüm fotoğraflarını al
    photos = Photo.objects.filter(user=request.user)
    
    # Filtreleme uygula
    if filter_type == 'images':
        photos = photos.filter(image__iregex=r'\.(jpg|jpeg|png|heic)$')
    elif filter_type == 'videos':
        photos = photos.filter(image__iregex=r'\.(mov|mp4|avi)$')
    
    # Thumbnail dizinini oluştur
    thumbnail_dir = os.path.join('media', 'thumbnails')
    os.makedirs(thumbnail_dir, exist_ok=True)
    
    # Küçük resimleri oluştur veya önbellekten al
    photo_list = []
    for photo in photos:
        thumb_name = f"thumb_{photo.image.name.split('/')[-1]}"  # Dosya adını al
        thumb_path = os.path.join(thumbnail_dir, thumb_name)
        
        if os.path.exists(thumb_path):
            thumbnail_url = f"/media/thumbnails/{thumb_name}"
        else:
            try:
                if photo.image.name.lower().endswith(('.jpg', '.jpeg', '.png', '.heic')):
                    # Resimler için küçük resim oluştur
                    img = Image.open(photo.image.path)
                    img.thumbnail((100, 100))
                    if img.mode in ('RGBA', 'P', 'LA'):
                        img = img.convert('RGB')
                    thumb_io = io.BytesIO()
                    img.save(thumb_io, format='JPEG')
                    thumb_io.seek(0)
                    with open(thumb_path, 'wb') as f:
                        f.write(thumb_io.getvalue())
                    thumbnail_url = f"/media/thumbnails/{thumb_name}"
                elif photo.image.name.lower().endswith(('.mov', '.mp4', '.avi')):
                    # Videolar için küçük resim oluştur (ffmpeg ile)
                    stream = ffmpeg.input(photo.image.path)
                    stream = ffmpeg.output(stream, thumb_path, vframes=1, format='image2', q_v=2)
                    ffmpeg.run(stream, overwrite_output=True)
                    thumbnail_url = f"/media/thumbnails/{thumb_name}"
                else:
                    thumbnail_url = None
            except Exception as e:
                print(f"Küçük resim oluşturulamadı: {photo.image.name} - {str(e)}")
                thumbnail_url = None
        
        photo_list.append({
            'id': photo.id,
            'filename': photo.image.name,
            'size': photo.image.size,
            'thumbnail': thumbnail_url,
        })
    
    # Sayfalamayı ekle
    paginator = Paginator(photo_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Şablona geçilecek veriler
    context = {
        'page_obj': page_obj,
        'current_filter': filter_type,
    }
    return render(request, 'photos/photo_list.html', context)

@login_required
def upload_photo(request):
    if request.method == 'POST':
        form = PhotoForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.user = request.user
            photo.save()
            return redirect('photo_list')
    else:
        form = PhotoForm()
    return render(request, 'photos/upload.html', {'form': form})

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

@login_required
def delete_all_photos(request):
    if request.method == 'POST':
        deleted_count, _ = Photo.objects.filter(user=request.user).delete()
        if deleted_count > 0:
            messages.success(request, "Tüm fotoğraflarınız silindi.")
        else:
            messages.warning(request, "Silinecek fotoğraf bulunamadı.")
    return redirect('photo_list')