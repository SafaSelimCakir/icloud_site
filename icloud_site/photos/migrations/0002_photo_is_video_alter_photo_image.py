# Generated by Django 5.1.7 on 2025-04-30 06:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='photo',
            name='is_video',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='photo',
            name='image',
            field=models.FileField(upload_to='photos/'),
        ),
    ]
