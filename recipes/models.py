from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.core.validators import FileExtensionValidator
from nutrition.models import Ingredient
from decimal import Decimal
import os


def recipe_image_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'recipes/{instance.slug}.{ext}'


def validate_image_size(image):
    from django.core.exceptions import ValidationError
    if image.size > 2 * 1024 * 1024:
        raise ValidationError("Image file too large (max 2 MB).")


class Recipe(models.Model):
    DIET_CHOICES = [
        ('vegetarian', 'Vegetarian'),
        ('vegan', 'Vegan'),
        ('eggetarian', 'Eggetarian'),
    ]
    MEAL_TYPE_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
        ('snack', 'Snack'),
        ('any', 'Any'),
    ]

    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recipes'
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to=recipe_image_upload_path,
        null=True, blank=True,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']),
            validate_image_size,
        ]
    )
    instructions = models.TextField()
    prep_time = models.PositiveIntegerField(default=0, help_text='Minutes')
    cook_time = models.PositiveIntegerField(default=0, help_text='Minutes')
    servings = models.PositiveIntegerField(default=1)
    diet_type = models.CharField(max_length=20, choices=DIET_CHOICES, default='vegetarian')
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES, default='any')
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['diet_type']),
            models.Index(fields=['meal_type']),
            models.Index(fields=['is_public']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            counter = 1
            while Recipe.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def total_time(self):
        return self.prep_time + self.cook_time

    @property
    def instructions_list(self):
        if not self.instructions:
            return []
        return [line.strip() for line in self.instructions.splitlines() if line.strip()]

    @property
    def recipeingredient_set(self):
        return self.recipe_ingredients

    @property
    def card_avatar(self):
        t = self.title.lower()
        if 'tofu' in t or 'paneer' in t or 'scramble' in t:
            return 'tofu'
        elif 'dal' in t or 'tomato' in t or 'curry' in t or 'soup' in t:
            return 'tomato'
        elif 'bowl' in t or 'rice' in t or 'chana' in t or 'rajma' in t or 'oat' in t or 'quinoa' in t:
            return 'bowl'
        choices = ['tofu', 'tomato', 'bowl']
        return choices[(self.pk or 0) % 3]

    @property
    def card_color(self):
        t = self.title.lower()
        if 'palak tofu' in t or 'rajma' in t:
            return '#F7C548'  # Yellow
        elif 'tomato dal' in t or 'chana' in t:
            return '#E55B3C'  # Coral
        elif 'quinoa' in t or 'oat' in t:
            return '#3697A5'  # Teal
        elif 'paneer' in t or 'scramble' in t:
            return '#A4C996'  # Sage
        colors = ['#F7C548', '#E55B3C', '#3697A5', '#A4C996']
        return colors[(self.pk or 0) % 4]

    @property
    def highlight_nutrient(self):
        n = getattr(self, 'nutrition', None)
        if not n:
            return f"{self.prep_time or 20} min"
        t = self.title.lower()
        if 'tomato dal' in t:
            return f"{round(n.iron)}mg iron"
        if 'quinoa' in t or 'rajma' in t:
            return f"{round(n.fiber)}g fiber"
        if 'paneer' in t:
            return f"{round(n.calcium)}mg calcium"
        if 'oat' in t and n.b12 > 0:
            return f"{round(n.b12, 1)}µg B12"
        if n.protein >= 15:
            return f"{round(n.protein)}g protein"
        if n.iron >= 5:
            return f"{round(n.iron)}mg iron"
        if n.fiber >= 7:
            return f"{round(n.fiber)}g fiber"
        if n.calcium >= 200:
            return f"{round(n.calcium)}mg calcium"
        if n.protein > 0:
            return f"{round(n.protein)}g protein"
        return f"{round(n.calories)} kcal"


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='recipe_ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE)
    quantity_grams = models.DecimalField(max_digits=10, decimal_places=2)
    display_text = models.CharField(max_length=200, blank=True, help_text='e.g. "1 cup"')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.ingredient.name} ({self.quantity_grams}g) in {self.recipe.title}"

    @property
    def grams(self):
        return self.quantity_grams


class RecipeNutrition(models.Model):
    recipe = models.OneToOneField(Recipe, on_delete=models.CASCADE, related_name='nutrition')
    is_manual = models.BooleanField(default=False)

    # Per-serving values
    calories = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    protein = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    carbs = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fat = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fiber = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sugar = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    iron = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    calcium = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    b12 = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    zinc = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    magnesium = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vitamin_c = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sodium = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    computed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Nutrition for {self.recipe.title}"

    @property
    def carbohydrates(self):
        return self.carbs
