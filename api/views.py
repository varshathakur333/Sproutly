"""
api/views.py — updated with nutrition preview endpoint
"""

from datetime import date as date_type

from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated

from nutrition.models import Ingredient, NutritionGoal
from recipes.models import Recipe, RecipeIngredient
from tracker.models import MealLog, Favorite
from nutrition.services import (
    get_user_goals, compute_progress, compute_daily_totals,
    ingredient_nutrients_for_grams, NUTRIENT_FIELDS,
)
from recipes.services import filter_recipes, sort_recipes, annotate_match_data, _parse_id_list
from tracker.services import (
    get_dashboard_data, get_recommendations, guess_next_meal_type,
    get_seven_day_trend, copy_log_entry,
)
from django.db.models import Q
from decimal import Decimal

from api.serializers import (
    IngredientSerializer,
    RecipeListSerializer,
    RecipeDetailSerializer,
    RecipeWriteSerializer,
    NutritionGoalSerializer,
    MealLogSerializer,
    DashboardSerializer,
    RecommendationSerializer,
)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user


class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


# ---------------------------------------------------------------------------
# Ingredient ViewSet
# ---------------------------------------------------------------------------

class IngredientViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = IngredientSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    search_fields      = ['name', 'category']

    def get_queryset(self):
        qs = Ingredient.objects.all()
        q = self.request.query_params.get('q', '').strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs


# ---------------------------------------------------------------------------
# Recipe ViewSet
# ---------------------------------------------------------------------------

class RecipeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return RecipeWriteSerializer
        if self.action == 'retrieve':
            return RecipeDetailSerializer
        return RecipeListSerializer

    def get_queryset(self):
        params = dict(self.request.query_params)
        # Flatten single-value lists from QueryDict
        flat_params = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                       for k, v in params.items()}

        # have_ids can be multi-value
        have_ids = self.request.query_params.getlist('have_ids')
        if have_ids:
            flat_params['have_ids'] = have_ids

        qs = filter_recipes(flat_params, user=self.request.user)

        sort   = flat_params.get('sort', 'newest')
        result = sort_recipes(qs, sort, have_ids or None)

        if have_ids and isinstance(result, list):
            annotate_match_data(result, have_ids)

        return result

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def favorite(self, request, pk=None):
        recipe = self.get_object()
        fav, created = Favorite.objects.get_or_create(user=request.user, recipe=recipe)
        if not created:
            fav.delete()
            return Response({'favorited': False})
        return Response({'favorited': True})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def log(self, request, pk=None):
        recipe = self.get_object()
        serializer = MealLogSerializer(data={
            'recipe':    recipe.id,
            'date':      request.data.get('date', date_type.today().isoformat()),
            'meal_type': request.data.get('meal_type', 'lunch'),
            'servings':  request.data.get('servings', '1'),
        }, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='preview_nutrition')
    def preview_nutrition(self, request):
        """
        Compute live nutrition preview for the recipe form.
        Body: { servings: int, ingredients: [{ingredient_id: int, grams: float}] }
        Returns per-serving nutrient dict.
        """
        data     = request.data
        servings = max(int(data.get('servings', 1)), 1)
        items    = data.get('ingredients', [])

        totals = {f: Decimal('0') for f in NUTRIENT_FIELDS}
        for item in items:
            try:
                ing   = Ingredient.objects.get(pk=item['ingredient_id'])
                grams = Decimal(str(item['grams']))
                contrib = ingredient_nutrients_for_grams(ing, grams)
                for f in NUTRIENT_FIELDS:
                    totals[f] += contrib[f]
            except (Ingredient.DoesNotExist, (KeyError, ValueError)):
                pass

        per_serving = {f: float(totals[f] / servings) for f in NUTRIENT_FIELDS}
        return Response(per_serving)


# ---------------------------------------------------------------------------
# NutritionGoal ViewSet
# ---------------------------------------------------------------------------

class NutritionGoalViewSet(viewsets.ModelViewSet):
    serializer_class   = NutritionGoalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NutritionGoal.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def reset_defaults(self, request):
        from nutrition.services import create_default_goals, DEFAULT_GOALS
        NutritionGoal.objects.filter(user=request.user).delete()
        goals = create_default_goals(request.user)
        return Response(NutritionGoalSerializer(goals, many=True).data)


# ---------------------------------------------------------------------------
# MealLog ViewSet
# ---------------------------------------------------------------------------

class MealLogViewSet(viewsets.ModelViewSet):
    serializer_class   = MealLogSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        qs = MealLog.objects.filter(user=self.request.user).select_related(
            'recipe', 'recipe__nutrition', 'ingredient'
        )
        date_str = self.request.query_params.get('date')
        if date_str:
            d = parse_date(date_str)
            if d:
                qs = qs.filter(date=d)
        meal_type = self.request.query_params.get('meal_type')
        if meal_type:
            qs = qs.filter(meal_type=meal_type)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def copy(self, request, pk=None):
        log = self.get_object()
        target_date_str = request.data.get('date')
        target_date = parse_date(target_date_str) if target_date_str else log.date
        target_meal = request.data.get('meal_type', log.meal_type)
        new_log = copy_log_entry(log, target_date=target_date, target_meal_type=target_meal)
        return Response(MealLogSerializer(new_log).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Search API view
# ---------------------------------------------------------------------------

@api_view(['GET'])
def search_api(request):
    """
    Search both recipes and ingredients by query string.
    Returns: { 'results': [ { 'id': int, 'name': str, 'type': 'recipe'|'ingredient' } ] }
    """
    q = request.query_params.get('q', '').strip()
    if not q:
        return Response({'results': []})

    recipes = Recipe.objects.filter(is_public=True).filter(
        Q(title__icontains=q) | Q(description__icontains=q)
    )[:6]

    ingredients = Ingredient.objects.filter(name__icontains=q)[:6]

    results = []
    for r in recipes:
        results.append({
            'id': r.id,
            'name': r.title,
            'type': 'recipe',
            'slug': r.slug,
        })
    for ing in ingredients:
        results.append({
            'id': ing.id,
            'name': ing.name,
            'type': 'ingredient',
        })

    return Response({'results': results})


# ---------------------------------------------------------------------------
# Dashboard API view
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_api(request):
    date_str = request.query_params.get('date', date_type.today().isoformat())
    date_val = parse_date(date_str) or date_type.today()
    data = get_dashboard_data(request.user, date_val)
    def _to_float(d):
        if isinstance(d, dict):
            return {k: _to_float(v) for k, v in d.items()}
        if hasattr(d, '__float__'):
            return float(d)
        return d
    return Response(_to_float(data))


# ---------------------------------------------------------------------------
# Recommendations API view
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recommendations_api(request):
    date_str  = request.query_params.get('date', date_type.today().isoformat())
    date_val  = parse_date(date_str) or date_type.today()
    meal_type = request.query_params.get('meal_type') or guess_next_meal_type()
    recipes   = get_recommendations(request.user, date_val, meal_type)
    serializer = RecommendationSerializer(recipes, many=True, context={'request': request})
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# 7-day trend API view
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def trend_api(request):
    date_str = request.query_params.get('date', date_type.today().isoformat())
    date_val = parse_date(date_str) or date_type.today()
    return Response(get_seven_day_trend(request.user, date_val))
