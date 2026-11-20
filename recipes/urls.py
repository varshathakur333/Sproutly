"""
recipes/urls.py
"""

from django.urls import path
from recipes import views

urlpatterns = [
    path('',                  views.recipe_list,   name='recipe_list'),
    path('new/',              views.recipe_create, name='recipe_create'),
    path('<slug:slug>/',      views.recipe_detail, name='recipe_detail'),
    path('<slug:slug>/edit/', views.recipe_edit,   name='recipe_edit'),
    path('<slug:slug>/delete/', views.recipe_delete, name='recipe_delete'),
]

