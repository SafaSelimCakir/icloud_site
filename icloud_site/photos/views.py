from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Photo
from .forms import PhotoForm

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
def photo_list(request):
    photos = Photo.objects.filter(user=request.user)
    return render(request, 'photos/photo_list.html', {'photos': photos})