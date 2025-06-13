from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from photos.models import Photo

class ICloudLoginForm(forms.Form):
    apple_id = forms.EmailField(label='Apple ID')
    password = forms.CharField(label='Parola', widget=forms.PasswordInput)

class PhotoUploadForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ['image']

class SignUpForm(UserCreationForm):
    email = forms.EmailField(max_length=254, required=True, help_text='Geçerli bir e-posta adresi girin.')

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')