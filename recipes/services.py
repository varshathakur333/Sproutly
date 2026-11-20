"""
recipes/services.py
-------------------
Recipe filtering, scoring, and ingredient-match logic.
All query-building and ranking lives here; views are thin.
"""

from decimal import Decimal
from django.db.models import Q, QuerySet, Prefetch
from django.contrib.auth.models import User

from nutrition.services import NUTRIENT_FIELDS


# ---------------------------------------------------------------------------
# Staple ingredients ignored during "ingredients I have" matching
# ---------------------------------------------------------------------------

STAPLE_CATEGORIES = {'oil', 'spice'}
STAPLE_NAMES = {
    'salt', 'water', 'oil', 'sugar', 'black pepper', 'pepper',
    'baking soda', 'baking powder', 'yeast',
}


def _is_staple(ingredient) -> bool:
    return (
        ingredient.is_staple
        or ingredient.category in STAPLE_CATEGORIES
        or ingredient.name.lower() in STAPLE_NAMES
    )


# ---------------------------------------------------------------------------
# Nutrient range filter helpers
# ---------------------------------------------------------------------------

NUTRIENT_RANGE_PARAMS = [
    # (param_prefix, nutrition_field)
    ('calories',  'calories'),
    ('protein',   'protein'),
    ('carbs',     'carbs'),
    ('fat',       'fat'),
    ('fiber',     'fiber'),
    ('iron',      'iron'),
    ('calcium',   'calcium'),
    ('b12',       'b12'),
]


def _apply_nutrient_range(qs: QuerySet, params: dict) -> QuerySet:
    """Filter recipes by min/max nutrient values via their RecipeNutrition."""
    for prefix, field in NUTRIENT_RANGE_PARAMS:
        min_val = params.get(f'{prefix}_min')
        max_val = params.get(f'{prefix}_max')
        if min_val:
            try:
                qs = qs.filter(**{f'nutrition__{field}__gte': Decimal(str(min_val))})
            except Exception:
                pass
        if max_val:
            try:
                qs = qs.filter(**{f'nutrition__{field}__lte': Decimal(str(max_val))})
            except Exception:
                pass
    return qs


# ---------------------------------------------------------------------------
# Preset filters
# ---------------------------------------------------------------------------

PRESETS = {
    'high_protein':  {'protein_min': 15},
    'iron_rich':     {'iron_min': 4},
    'low_calorie':   {'calories_max': 400},
    'high_fiber':    {'fiber_min': 8},
    'vegan':         {'diet_type': 'vegan'},
    'under_20':      {'max_prep_time': 20},
    'under 20 min':  {'max_prep_time': 20},
}


# ---------------------------------------------------------------------------
# Main filter function
# ---------------------------------------------------------------------------

def filter_recipes(
    params: dict,
    user: User | None = None,
    base_qs: QuerySet | None = None,
) -> QuerySet:
    """
    Apply all recipe filters from a dict of query parameters.

    Supported params:
        q              – text search (title, description, ingredient names)
        diet_type      – vegetarian / vegan / eggetarian
        meal_type      – breakfast / lunch / dinner / snack / any
        max_prep_time  – integer minutes
        calories_min/max, protein_min/max, carbs_min/max, fat_min/max,
        fiber_min/max, iron_min/max, calcium_min/max, b12_min/max
        preset         – high_protein | iron_rich | low_calorie | high_fiber
        must_include   – list of ingredient IDs
        must_exclude   – list of ingredient IDs
        have_ids       – list of ingredient IDs (for "ingredients I have" scoring)
        tab            – 'mine' | 'favorites' | 'all'
        sort           – protein_desc | calories_asc | newest | match_score

    Returns an *unevaluated* QuerySet (caller must paginate).
    """
    from recipes.models import Recipe, RecipeIngredient

    if base_qs is None:
        base_qs = Recipe.objects.select_related('author', 'nutrition').prefetch_related(
            Prefetch(
                'recipe_ingredients',
                queryset=RecipeIngredient.objects.select_related('ingredient'),
            )
        )

    # --- Preset unpacking ---
    preset_key = params.get('preset')
    if preset_key and preset_key in PRESETS:
        params = {**params, **PRESETS[preset_key]}

    # --- Visibility ---
    if user and user.is_authenticated:
        tab = params.get('tab', 'all')
        if tab == 'mine':
            base_qs = base_qs.filter(author=user)
        elif tab == 'favorites':
            base_qs = base_qs.filter(favorited_by__user=user)
        else:
            base_qs = base_qs.filter(Q(is_public=True) | Q(author=user))
    else:
        base_qs = base_qs.filter(is_public=True)

    # --- Text search ---
    q = params.get('q', '').strip()
    if q:
        base_qs = base_qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(recipe_ingredients__ingredient__name__icontains=q)
        ).distinct()

    # --- Diet / meal type ---
    if params.get('diet_type'):
        base_qs = base_qs.filter(diet_type=params['diet_type'])
    if params.get('meal_type'):
        base_qs = base_qs.filter(meal_type=params['meal_type'])

    # --- Max prep time ---
    if params.get('max_prep_time'):
        try:
            base_qs = base_qs.filter(prep_time__lte=int(params['max_prep_time']))
        except (ValueError, TypeError):
            pass

    # --- Preset ---
    preset_key = params.get('preset')
    if preset_key and preset_key in PRESETS:
        params = {**params, **PRESETS[preset_key]}

    # --- Nutrient ranges ---
    base_qs = _apply_nutrient_range(base_qs, params)

    # --- Must include / exclude ingredients ---
    must_include = _parse_id_list(params.get('must_include'))
    for ing_id in must_include:
        base_qs = base_qs.filter(recipe_ingredients__ingredient_id=ing_id)

    must_exclude = _parse_id_list(params.get('must_exclude'))
    for ing_id in must_exclude:
        base_qs = base_qs.exclude(recipe_ingredients__ingredient_id=ing_id)

    # --- Distinct after any join-based filters ---
    base_qs = base_qs.distinct()

    return base_qs


# ---------------------------------------------------------------------------
# Sorting (applied after filtering, may require Python-side for match_score)
# ---------------------------------------------------------------------------

def sort_recipes(qs: QuerySet, sort: str, have_ids: list | None = None) -> QuerySet | list:
    """
    Sort a filtered queryset.  Returns a list when sort='match_score' because
    Python-side scoring is needed.
    """
    if sort == 'protein_desc':
        return qs.order_by('-nutrition__protein')
    if sort == 'calories_asc':
        return qs.order_by('nutrition__calories')
    if sort == 'newest':
        return qs.order_by('-created_at')
    if sort == 'match_score' and have_ids:
        return _sort_by_match_score(qs, have_ids)
    # Default: newest
    return qs.order_by('-created_at')


# ---------------------------------------------------------------------------
# Ingredient match scoring
# ---------------------------------------------------------------------------

def compute_ingredient_match(recipe, have_ids: set) -> dict:
    """
    Score a recipe by how many of its non-staple ingredients the user has.

    Returns:
        {
            'score':    float  0.0–1.0
            'matched':  int
            'total':    int    (non-staple ingredients only)
            'missing':  list of ingredient name strings
        }
    """
    non_staples = [
        ri for ri in recipe.recipe_ingredients.all()
        if not _is_staple(ri.ingredient)
    ]
    total = len(non_staples)
    if total == 0:
        return {'score': 1.0, 'matched': 0, 'total': 0, 'missing': []}

    matched = sum(1 for ri in non_staples if ri.ingredient_id in have_ids)
    missing = [ri.ingredient.name for ri in non_staples if ri.ingredient_id not in have_ids]
    return {
        'score':   matched / total,
        'matched': matched,
        'total':   total,
        'missing': missing,
    }


def _sort_by_match_score(qs: QuerySet, have_ids: list) -> list:
    """
    Evaluate the queryset, attach match data, and return sorted list.
    Each recipe gets a `.match` attribute with the result of compute_ingredient_match.
    """
    have_set = set(int(i) for i in have_ids if str(i).isdigit())
    recipes = list(qs)
    for recipe in recipes:
        recipe.match = compute_ingredient_match(recipe, have_set)
    recipes.sort(key=lambda r: r.match['score'], reverse=True)
    return recipes


def annotate_match_data(recipes, have_ids: list) -> list:
    """
    Attach match data to an iterable of recipes (already evaluated).
    Returns the same list with `.match` added to each recipe.
    """
    have_set = set(int(i) for i in have_ids if str(i).isdigit())
    for recipe in recipes:
        if not hasattr(recipe, 'match'):
            recipe.match = compute_ingredient_match(recipe, have_set)
    return recipes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_id_list(value) -> list:
    """Parse a comma/space/multi-value param into a list of integers."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        ids = value
    else:
        ids = str(value).replace(',', ' ').split()
    result = []
    for v in ids:
        try:
            result.append(int(v))
        except (ValueError, TypeError):
            pass
    return result

