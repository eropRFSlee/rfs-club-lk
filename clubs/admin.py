from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Club, UserProfile

@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ['id', 'sport_name', 'rfs_id', 'fifa_id', 'ogrn', 'email', 'aff_name', 'get_users']
    list_display_links = ['id', 'sport_name']
    search_fields = ['sport_name', 'rfs_id', 'fifa_id', 'ogrn', 'email', 'aff_name']
    list_per_page = 50
    
    def get_users(self, obj):
        if obj.user.exists():
            return ", ".join([u.username for u in obj.user.all()])
        return "—"
    get_users.short_description = 'Пользователи'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'rights']
    list_filter = ['rights']
    search_fields = ['user__username']


class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'get_rights']
    
    def get_rights(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.rights
        return 0
    get_rights.short_description = 'Права'


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)