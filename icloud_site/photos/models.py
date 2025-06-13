from django.db import models
from django.contrib.auth.models import User
import mimetypes

class Photo(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.FileField(upload_to='photos/')
    is_video = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.image:
            mime_type, _ = mimetypes.guess_type(self.image.name)
            self.is_video = bool(mime_type and mime_type.startswith('video'))
        super().save(*args, **kwargs)

    def __str__(self):
<<<<<<< HEAD
        return f"{self.user.username}'s photo"
    
    @property
    def is_video(self):
        return self.image.name.lower().endswith(('.mp4', '.mov', '.webm'))
=======
        return self.image.name
>>>>>>> 84f6ae9fa447953beb100393ebd56c6a60aaa695
