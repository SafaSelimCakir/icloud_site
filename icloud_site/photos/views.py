from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from pyicloud import PyiCloudService
from .forms import ICloudLoginForm, PhotoForm
from .models import Photo
from django.core.files.base import ContentFile
from django.contrib import messages

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
                    # API nesnesini değil, yalnızca kimlik bilgilerini sakla
                    request.session['icloud_credentials'] = {'apple_id': apple_id, 'password': password}
                    return redirect('icloud_2fa')
                # 2FA yoksa doğrudan seçim ekranına git
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
                # 2FA doğrulandı, seçim ekranına git
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
    api = PyiCloudService(apple_id, password)  # Yeni bir API nesnesi oluştur
    photos = api.photos.all
    
    if request.method == 'POST':
        selected_photo_ids = request.POST.getlist('photo_ids')
        for photo in photos:
            if photo.id in selected_photo_ids:
                response = photo.download()
                if response and response.status_code == 200:
                    photo_data = response.content
                    photo_instance = Photo(user=request.user)
                    photo_instance.image.save(photo.filename, ContentFile(photo_data))
                    photo_instance.save()
        messages.success(request, "Seçilen fotoğraflar eklendi.")
        del request.session['icloud_credentials']  # Session'ı temizle
        return redirect('photo_list')
    
    return render(request, 'photos/icloud_select.html', {'photos': photos})

@login_required
def photo_list(request):
    photos = Photo.objects.filter(user=request.user)
    return render(request, 'photos/photo_list.html', {'photos': photos})

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