from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal


class Ingredient(models.Model):
    CATEGORY_CHOICES = [
        ('legume', 'Legume'),
        ('grain', 'Grain'),
        ('vegetable', 'Vegetable'),
        ('fruit', 'Fruit'),
        ('dairy', 'Dairy'),
        ('nut_seed', 'Nut & Seed'),
        ('oil', 'Oil'),
        ('spice', 'Spice'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    is_vegan = models.BooleanField(default=True)

    # Nutrients per 100g
    calories = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    protein = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    carbs = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fat = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fiber = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    sugar = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    iron = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    calcium = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    b12 = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    zinc = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    magnesium = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    vitamin_c = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    sodium = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    external_id = models.CharField(max_length=100, null=True, blank=True, unique=True)

    # Staple flag - used to ignore in ingredient matching
    is_staple = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_vegan']),
        ]

    def __str__(self):
        return self.name


class NutritionGoal(models.Model):
    NUTRIENT_CHOICES = [
        ('calories', 'Calories'),
        ('protein', 'Protein'),
        ('carbs', 'Carbs'),
        ('fat', 'Fat'),
        ('fiber', 'Fiber'),
        ('iron', 'Iron'),
        ('calcium', 'Calcium'),
        ('b12', 'Vitamin B12'),
        ('zinc', 'Zinc'),
    ]
    UNIT_CHOICES = [
        ('kcal', 'kcal'),
        ('g', 'g'),
        ('mg', 'mg'),
        ('µg', 'µg'),
    ]
    GOAL_TYPE_CHOICES = [
        ('minimum', 'Minimum'),
        ('maximum', 'Maximum'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='nutrition_goals')
    nutrient = models.CharField(max_length=50, choices=NUTRIENT_CHOICES)
    target_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    goal_type = models.CharField(max_length=10, choices=GOAL_TYPE_CHOICES, default='minimum')

    class Meta:
        unique_together = ('user', 'nutrient')
        ordering = ['nutrient']

    def __str__(self):
        return f"{self.user.username} - {self.nutrient}: {self.goal_type} {self.target_amount} {self.unit}"
