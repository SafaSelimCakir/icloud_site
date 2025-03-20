from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_photo, name='upload_photo'),
    path('', views.photo_list, name='photo_list'),
    path('icloud/', views.icloud_login, name='icloud_login'),
    path('icloud/2fa/', views.icloud_2fa, name='icloud_2fa'),
    path('icloud/select/', views.icloud_select_photos, name='icloud_select_photos'),
    path('delete/', views.delete_photos, name='delete_photos'),
    path('delete-all/', views.delete_all_photos, name='delete_all_photos'),
]