from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView

app_name = 'photos'

urlpatterns = [
    path('', views.photo_list, name='photo_list'),
    path('icloud/', views.icloud_login, name='icloud_login'),
    path('icloud/2fa/', views.icloud_2fa, name='icloud_2fa'),
    path('icloud/select/', views.icloud_select_photos, name='icloud_select_photos'),
    path('upload/', views.upload_photo, name='upload_photo'),
    path('delete/', views.delete_photos, name='delete_photos'),
    path('delete_all/', views.delete_all_photos, name='delete_all_photos'),
    path('delete_account/', views.delete_account, name='delete_account'),
    path('download/<int:photo_id>/', views.download_photo, name='download_photo'),
<<<<<<< HEAD
    

]
=======
    path('signup/', views.sign_up, name='sign_up'),
    path('login/', LoginView.as_view(template_name='photos/login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('play/<int:photo_id>/', views.play_video, name='play_video'),
]   
>>>>>>> 84f6ae9fa447953beb100393ebd56c6a60aaa695
