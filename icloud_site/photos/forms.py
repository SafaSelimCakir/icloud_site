from django import forms
from photos.models import Photo

class ICloudLoginForm(forms.Form):
    apple_id = forms.EmailField(label='Apple ID')
    password = forms.CharField(label='Parola', widget=forms.PasswordInput)

class PhotoUploadForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ['image']