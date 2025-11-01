from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    
    path('login/', views.login_view, name='login'),

    path('register/', views.choose_role_view, name='choose_role'),
    path('register/user-info/<str:role>/', views.register_user_info, name='register_user_info'),
    path('verify/<str:token>/', views.verify_email, name='verify_email'),
    path('register/organization/<str:token>/', views.register_organization, name='register_organization'),
    
    path('logout/', views.logout_view, name='logout'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
