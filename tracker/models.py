from django.db import models
from django.contrib.auth.models import User
from recipes.models import Recipe
from nutrition.models import Ingredient
from decimal import Decimal


class MealLog(models.Model):
    MEAL_TYPE_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
        ('snack', 'Snack'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meal_logs')
    date = models.DateField()
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES)
    recipe = models.ForeignKey(Recipe, on_delete=models.SET_NULL, null=True, blank=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.SET_NULL, null=True, blank=True)
    servings = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1.0'))
    logged_at = models.DateTimeField(auto_now_add=True)

    # Nutrient snapshot (per total servings logged)
    snap_calories = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_protein = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_carbs = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_fat = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_fiber = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_sugar = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_iron = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_calcium = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_b12 = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    snap_zinc = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_magnesium = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_vitamin_c = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    snap_sodium = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['date', 'meal_type', 'logged_at']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'date', 'meal_type']),
        ]

    def __str__(self):
        name = self.recipe.title if self.recipe else (self.ingredient.name if self.ingredient else 'Unknown')
        return f"{self.user.username} - {self.date} {self.meal_type}: {name}"

    def save(self, *args, **kwargs):
        self._compute_snapshot()
        super().save(*args, **kwargs)

    def _compute_snapshot(self):
        from tracker.services import compute_log_nutrients
        nutrients = compute_log_nutrients(self)
        for key, val in nutrients.items():
            setattr(self, f'snap_{key}', val)

    @property
    def calories_snapshot(self):
        return self.snap_calories

    @property
    def protein_snapshot(self):
        return self.snap_protein


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'recipe')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} ♥ {self.recipe.title}"
