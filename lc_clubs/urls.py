from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from clubs import views as clubs_views

urlpatterns = [
    # АДМИН-ВЕРИФИКАЦИЯ
    path('admin/verify/', clubs_views.admin_verify_documents, name='admin_verify'),
    path('admin/verify-action/', clubs_views.admin_verify_action, name='admin_verify_action'),
    
    # СТАНДАРТНАЯ АДМИНКА
    path('admin/', admin.site.urls),
    
    # КАСТОМНЫЙ ВХОД (ПЕРЕНАПРАВЛЯЕТ СУПЕРПОЛЬЗОВАТЕЛЯ НА /admin/verify/)
    path('accounts/login/', clubs_views.custom_login, name='login'),
    
    # ВЫХОД
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('clubs.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)