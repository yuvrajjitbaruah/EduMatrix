from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as account_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', account_views.landing_view, name='home'),
    path('about/', account_views.public_page_view, {'page_slug': 'about'}, name='about'),
    path('contact/', account_views.public_page_view, {'page_slug': 'contact'}, name='contact'),
    path('terms/', account_views.public_page_view, {'page_slug': 'terms'}, name='terms_short'),
    path('terms-and-conditions/', account_views.public_page_view, {'page_slug': 'terms'}, name='terms'),
    path('privacy/', account_views.public_page_view, {'page_slug': 'privacy'}, name='privacy_short'),
    path('privacy-policy/', account_views.public_page_view, {'page_slug': 'privacy'}, name='privacy'),
    path('offline/', account_views.offline_view, name='offline'),
    path('service-worker.js', account_views.service_worker_view, name='service_worker'),
    path('', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('quizzes/', include('quizzes.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
