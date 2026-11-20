"""tracker/admin.py"""

from django.contrib import admin
from tracker.models import MealLog, Favorite


@admin.register(MealLog)
class MealLogAdmin(admin.ModelAdmin):
    list_display  = ('user', 'date', 'meal_type', 'recipe', 'ingredient', 'servings', 'snap_calories', 'snap_protein')
    list_filter   = ('meal_type', 'date')
    search_fields = ('user__username', 'recipe__title', 'ingredient__name')
    ordering      = ('-date', 'meal_type')


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display  = ('user', 'recipe', 'created_at')
    search_fields = ('user__username', 'recipe__title')
