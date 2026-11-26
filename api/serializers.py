"""
api/serializers.py
DRF serializers for all Sproutly models.
"""

from decimal import Decimal
from django.contrib.auth.models import User
from rest_framework import serializers

from nutrition.models import Ingredient, NutritionGoal
from recipes.models import Recipe, RecipeIngredient, RecipeNutrition
from tracker.models import MealLog, Favorite


# ---------------------------------------------------------------------------
# Ingredient
# ---------------------------------------------------------------------------

class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Ingredient
        fields = [
            'id', 'name', 'category', 'is_vegan', 'is_staple',
            'calories', 'protein', 'carbs', 'fat', 'fiber', 'sugar',
            'iron', 'calcium', 'b12', 'zinc', 'magnesium', 'vitamin_c', 'sodium',
        ]


# ---------------------------------------------------------------------------
# Recipe Nutrition
# ---------------------------------------------------------------------------

class RecipeNutritionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecipeNutrition
        fields = [
            'calories', 'protein', 'carbs', 'fat', 'fiber', 'sugar',
            'iron', 'calcium', 'b12', 'zinc', 'magnesium', 'vitamin_c', 'sodium',
            'is_manual', 'computed_at',
        ]


# ---------------------------------------------------------------------------
# Recipe Ingredient
# ---------------------------------------------------------------------------

class RecipeIngredientSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source='ingredient.name', read_only=True)

    class Meta:
        model  = RecipeIngredient
        fields = ['id', 'ingredient', 'ingredient_name', 'quantity_grams', 'display_text']


# ---------------------------------------------------------------------------
# Recipe (list)
# ---------------------------------------------------------------------------

class RecipeListSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    nutrition   = RecipeNutritionSerializer(read_only=True)
    total_time  = serializers.IntegerField(read_only=True)
    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model  = Recipe
        fields = [
            'id', 'slug', 'title', 'description', 'image',
            'diet_type', 'meal_type', 'prep_time', 'cook_time', 'total_time',
            'servings', 'is_public', 'created_at',
            'author_name', 'nutrition', 'is_favorite',
        ]

    def get_author_name(self, obj):
        return obj.author.username if obj.author else 'Sproutly'

    def get_is_favorite(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.favorited_by.filter(user=request.user).exists()
        return False


# ---------------------------------------------------------------------------
# Recipe (detail)
# ---------------------------------------------------------------------------

class RecipeDetailSerializer(RecipeListSerializer):
    recipe_ingredients = RecipeIngredientSerializer(many=True, read_only=True)
    instructions_html  = serializers.SerializerMethodField()

    class Meta(RecipeListSerializer.Meta):
        fields = RecipeListSerializer.Meta.fields + [
            'instructions', 'instructions_html', 'recipe_ingredients',
        ]

    def get_instructions_html(self, obj):
        # Simple newline → <p> conversion for display
        return obj.instructions


# ---------------------------------------------------------------------------
# Recipe (write)
# ---------------------------------------------------------------------------

class RecipeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Recipe
        fields = [
            'title', 'description', 'instructions', 'image',
            'prep_time', 'cook_time', 'servings',
            'diet_type', 'meal_type', 'is_public',
        ]

    def create(self, validated_data):
        request = self.context['request']
        return Recipe.objects.create(author=request.user, **validated_data)


# ---------------------------------------------------------------------------
# NutritionGoal
# ---------------------------------------------------------------------------

class NutritionGoalSerializer(serializers.ModelSerializer):
    class Meta:
        model  = NutritionGoal
        fields = ['id', 'nutrient', 'target_amount', 'unit', 'goal_type']

    def validate_target_amount(self, value):
        from nutrition.services import validate_goal_bounds
        nutrient = self.initial_data.get('nutrient', '')
        ok, msg = validate_goal_bounds(nutrient, Decimal(str(value)))
        if not ok:
            raise serializers.ValidationError(msg)
        return value


# ---------------------------------------------------------------------------
# MealLog
# ---------------------------------------------------------------------------

class MealLogSerializer(serializers.ModelSerializer):
    recipe_title      = serializers.CharField(source='recipe.title', read_only=True)
    ingredient_name   = serializers.CharField(source='ingredient.name', read_only=True)
    recipe_slug       = serializers.CharField(source='recipe.slug', read_only=True)
    recipe_image      = serializers.ImageField(source='recipe.image', read_only=True)

    class Meta:
        model  = MealLog
        fields = [
            'id', 'date', 'meal_type', 'servings', 'logged_at',
            'recipe', 'recipe_title', 'recipe_slug', 'recipe_image',
            'ingredient', 'ingredient_name',
            'custom_food_name', 'custom_calories',
            'snap_calories', 'snap_protein', 'snap_carbs', 'snap_fat',
            'snap_fiber', 'snap_iron', 'snap_calcium', 'snap_b12',
            'snap_zinc', 'snap_magnesium', 'snap_vitamin_c', 'snap_sodium',
        ]
        read_only_fields = [
            'logged_at',
            'snap_calories', 'snap_protein', 'snap_carbs', 'snap_fat',
            'snap_fiber', 'snap_iron', 'snap_calcium', 'snap_b12',
            'snap_zinc', 'snap_magnesium', 'snap_vitamin_c', 'snap_sodium',
        ]

    def validate(self, data):
        # Support 'calories' alias if sent by clients
        if 'calories' in self.initial_data and 'custom_calories' not in data:
            data['custom_calories'] = self.initial_data['calories']
        if 'food_name' in self.initial_data and 'custom_food_name' not in data:
            data['custom_food_name'] = self.initial_data['food_name']

        recipe = data.get('recipe', getattr(self.instance, 'recipe', None))
        ingredient = data.get('ingredient', getattr(self.instance, 'ingredient', None))
        custom_food_name = data.get('custom_food_name', getattr(self.instance, 'custom_food_name', None))
        if not recipe and not ingredient and not custom_food_name:
            raise serializers.ValidationError("Provide a recipe, an ingredient, or custom food name.")
        return data

    def create(self, validated_data):
        if 'user' not in validated_data and 'request' in self.context:
            validated_data['user'] = self.context['request'].user
        return MealLog.objects.create(**validated_data)


# ---------------------------------------------------------------------------
# Dashboard (read-only)
# ---------------------------------------------------------------------------

class DashboardSerializer(serializers.Serializer):
    totals   = serializers.DictField()
    goals    = serializers.DictField()
    progress = serializers.DictField()
    summary  = serializers.CharField()


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

class RecommendationSerializer(serializers.ModelSerializer):
    nutrition  = RecipeNutritionSerializer(read_only=True)
    rec_badge  = serializers.CharField(read_only=True)
    rec_score  = serializers.FloatField(read_only=True)

    class Meta:
        model  = Recipe
        fields = ['id', 'slug', 'title', 'image', 'diet_type', 'meal_type',
                  'prep_time', 'cook_time', 'nutrition', 'rec_badge', 'rec_score']

