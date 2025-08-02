from django.contrib import admin
from django.urls import path, include

# --- Add these two imports ---
from django.conf import settings
from django.conf.urls.static import static # <-- This line is now correct

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('inventory.urls')),
]

# --- Add this line at the end ---
# This tells Django to serve static files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)