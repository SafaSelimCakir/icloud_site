from django import forms
from .models import Photo

class PhotoForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ['image']

class ICloudLoginForm(forms.Form):
    apple_id = forms.EmailField(label='Apple ID')
    password = forms.CharField(label='Şifre', widget=forms.PasswordInput)