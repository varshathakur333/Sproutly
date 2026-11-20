"""recipes/admin.py"""

from django.contrib import admin
from recipes.models import Recipe, RecipeIngredient, RecipeNutrition


class RecipeIngredientInline(admin.TabularInline):
    model  = RecipeIngredient
    extra  = 1
    fields = ('ingredient', 'quantity_grams', 'display_text')


class RecipeNutritionInline(admin.StackedInline):
    model  = RecipeNutrition
    extra  = 0
    fields = (
        'is_manual',
        ('calories', 'protein', 'carbs', 'fat'),
        ('fiber', 'sugar', 'iron', 'calcium'),
        ('b12', 'zinc', 'magnesium', 'vitamin_c', 'sodium'),
    )


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display   = ('title', 'author', 'diet_type', 'meal_type', 'is_public', 'created_at')
    list_filter    = ('diet_type', 'meal_type', 'is_public')
    search_fields  = ('title', 'description')
    prepopulated_fields = {'slug': ('title',)}
    inlines        = [RecipeIngredientInline, RecipeNutritionInline]
    ordering       = ('-created_at',)
