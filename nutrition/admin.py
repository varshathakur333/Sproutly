"""nutrition/admin.py"""

from django.contrib import admin
from nutrition.models import Ingredient, NutritionGoal


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display  = ('name', 'category', 'is_vegan', 'is_staple', 'calories', 'protein', 'iron', 'calcium')
    list_filter   = ('category', 'is_vegan', 'is_staple')
    search_fields = ('name',)
    ordering      = ('name',)


@admin.register(NutritionGoal)
class NutritionGoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'nutrient', 'target_amount', 'unit', 'goal_type')
    list_filter  = ('nutrient', 'goal_type')
    search_fields = ('user__username',)
