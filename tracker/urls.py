"""
tracker/urls.py
"""

from django.urls import path
from tracker import views

urlpatterns = [
    path('',           views.home,       name='home'),
    path('tracker/',   views.tracker,    name='tracker'),
    path('dashboard/', views.dashboard,  name='dashboard'),
    path('goals/',     views.goals,      name='goals'),
]

