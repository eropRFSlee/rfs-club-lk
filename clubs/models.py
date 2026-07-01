from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify

class Club(models.Model):
    sport_name = models.CharField(max_length=200, verbose_name='Спортивное название')
    # МЕНЯЕМ ForeignKey НА ManyToManyField
    user = models.ManyToManyField(User, blank=True, related_name='clubs')
    slug = models.SlugField(unique=True, blank=True, null=True)
    
    rfs_id = models.CharField(max_length=50, blank=True, verbose_name='РФС ID')
    fifa_id = models.CharField(max_length=50, blank=True, verbose_name='FIFA ID')
    ogrn = models.CharField(max_length=50, blank=True, verbose_name='ОГРН')
    
    email = models.EmailField(blank=True, verbose_name='Общий e-mail')
    aff_name = models.CharField(max_length=200, blank=True, verbose_name='Аффилированные организации')
    
    def __str__(self):
        return self.sport_name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.sport_name)
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    rights = models.IntegerField(default=0, verbose_name='Права доступа (1 - полный доступ)')
    
    def __str__(self):
        return f"{self.user.username} - rights: {self.rights}"