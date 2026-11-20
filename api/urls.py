"""api/urls.py"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api import views

router = DefaultRouter()
router.register(r'ingredients', views.IngredientViewSet, basename='ingredient')
router.register(r'recipes',     views.RecipeViewSet,    basename='recipe')
router.register(r'goals',       views.NutritionGoalViewSet, basename='goal')
router.register(r'logs',        views.MealLogViewSet,   basename='meallog')

urlpatterns = [
    path('', include(router.urls)),
    path('search/',    views.search_api,          name='api-search'),
    path('dashboard/', views.dashboard_api,      name='api-dashboard'),
    path('recommendations/', views.recommendations_api, name='api-recommendations'),
    path('trend/',     views.trend_api,           name='api-trend'),
]

