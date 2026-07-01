from django.urls import path
from . import views

app_name = 'clubs'

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('api/deals/', views.get_deals, name='get_deals'),
    path('api/club-data/', views.get_club_data, name='get_club_data'),
    path('api/club-document/', views.get_club_document, name='get_club_document'),
    path('api/upload-club-document/', views.upload_club_document, name='upload_club_document'),
    path('api/delete-club-document/', views.delete_club_document, name='delete_club_document'),
    path('download-document/<str:doc_type>/', views.download_club_document, name='download_document'),
    path('download-document-admin/<str:doc_type>/', views.download_club_document_by_club, name='download_document_admin'),
]