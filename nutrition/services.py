"""
nutrition/services.py
---------------------
Pure business-logic functions for nutrient calculation and goal management.
No view or request logic here — only data in, data out.
"""

from decimal import Decimal, ROUND_HALF_UP
from django.contrib.auth.models import User
from django.db import transaction

from nutrition.models import Ingredient, NutritionGoal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUTRIENT_FIELDS = [
    'calories', 'protein', 'carbs', 'fat', 'fiber',
    'sugar', 'iron', 'calcium', 'b12', 'zinc',
    'magnesium', 'vitamin_c', 'sodium',
]

# Nutrients shown prominently in the UI (subset used for dashboard/goals)
PRIMARY_NUTRIENTS = ['calories', 'protein', 'carbs', 'fat', 'fiber', 'iron', 'calcium', 'b12', 'zinc']

# Default goals created for every new user
DEFAULT_GOALS = [
    {'nutrient': 'calories',  'target_amount': Decimal('2000'),  'unit': 'kcal', 'goal_type': 'minimum'},
    {'nutrient': 'protein',   'target_amount': Decimal('60'),    'unit': 'g',    'goal_type': 'minimum'},
    {'nutrient': 'carbs',     'target_amount': Decimal('250'),   'unit': 'g',    'goal_type': 'minimum'},
    {'nutrient': 'fat',       'target_amount': Decimal('65'),    'unit': 'g',    'goal_type': 'maximum'},
    {'nutrient': 'fiber',     'target_amount': Decimal('30'),    'unit': 'g',    'goal_type': 'minimum'},
    {'nutrient': 'iron',      'target_amount': Decimal('18'),    'unit': 'mg',   'goal_type': 'minimum'},
    {'nutrient': 'calcium',   'target_amount': Decimal('1000'),  'unit': 'mg',   'goal_type': 'minimum'},
    {'nutrient': 'b12',       'target_amount': Decimal('2.4'),   'unit': 'µg',   'goal_type': 'minimum'},
    {'nutrient': 'zinc',      'target_amount': Decimal('8'),     'unit': 'mg',   'goal_type': 'minimum'},
]

# Validation bounds: {nutrient: (min_allowed, max_allowed)}
GOAL_BOUNDS = {
    'calories': (Decimal('500'),    Decimal('10000')),
    'protein':  (Decimal('10'),     Decimal('500')),
    'carbs':    (Decimal('20'),     Decimal('1000')),
    'fat':      (Decimal('10'),     Decimal('500')),
    'fiber':    (Decimal('5'),      Decimal('200')),
    'iron':     (Decimal('1'),      Decimal('200')),
    'calcium':  (Decimal('100'),    Decimal('5000')),
    'b12':      (Decimal('0.1'),    Decimal('100')),
    'zinc':     (Decimal('1'),      Decimal('100')),
}


# ---------------------------------------------------------------------------
# Rounding helpers
# ---------------------------------------------------------------------------

def _round_nutrient(value: Decimal, nutrient: str) -> Decimal:
    """Round to 2 decimal places for µg nutrients (b12), 1 dp for everything else."""
    if nutrient == 'b12':
        return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)


def round_nutrients(nutrient_dict: dict) -> dict:
    """Return a new dict with all nutrient values rounded for display."""
    return {k: _round_nutrient(Decimal(str(v)), k) for k, v in nutrient_dict.items()}


# ---------------------------------------------------------------------------
# Per-ingredient nutrient contribution
# ---------------------------------------------------------------------------

def ingredient_nutrients_for_grams(ingredient: Ingredient, grams: Decimal) -> dict:
    """
    Return the absolute nutrient values contributed by `grams` of `ingredient`.
    Formula: ingredient_per_100g × grams / 100
    """
    factor = Decimal(str(grams)) / Decimal('100')
    return {
        field: Decimal(str(getattr(ingredient, field, 0))) * factor
        for field in NUTRIENT_FIELDS
    }


# ---------------------------------------------------------------------------
# Recipe nutrition calculation
# ---------------------------------------------------------------------------

def compute_recipe_nutrition(recipe) -> dict:
    """
    Sum nutrients across all RecipeIngredient rows and divide by servings.
    Returns a dict of per-serving nutrient values (Decimal, unrounded).

    Works with a Recipe instance that has prefetched/selected recipe_ingredients
    with their related ingredient objects.
    """
    totals = {field: Decimal('0') for field in NUTRIENT_FIELDS}
    servings = Decimal(str(max(recipe.servings, 1)))

    for ri in recipe.recipe_ingredients.select_related('ingredient').all():
        contrib = ingredient_nutrients_for_grams(ri.ingredient, ri.quantity_grams)
        for field in NUTRIENT_FIELDS:
            totals[field] += contrib[field]

    return {field: totals[field] / servings for field in NUTRIENT_FIELDS}


def save_recipe_nutrition(recipe, manual_data: dict | None = None) -> 'RecipeNutrition':
    """
    Compute (or accept manual) nutrition for a recipe and persist it.
    Creates a RecipeNutrition row if one does not exist.

    Args:
        recipe:       Recipe instance
        manual_data:  If provided, use these values instead of computing them.
                      Keys must match NUTRIENT_FIELDS.

    Returns:
        The saved RecipeNutrition instance.
    """
    from recipes.models import RecipeNutrition

    if manual_data:
        values = {field: Decimal(str(manual_data.get(field, 0))) for field in NUTRIENT_FIELDS}
        is_manual = True
    else:
        values = compute_recipe_nutrition(recipe)
        is_manual = False

    nutrition, _ = RecipeNutrition.objects.get_or_create(recipe=recipe)
    nutrition.is_manual = is_manual
    for field, value in values.items():
        setattr(nutrition, field, value)
    nutrition.save()
    return nutrition


# ---------------------------------------------------------------------------
# Meal-log nutrient snapshot
# ---------------------------------------------------------------------------

def compute_log_nutrients(meal_log) -> dict:
    """
    Compute the nutrient snapshot for a MealLog row.

    Priority:
      1. If the log references a Recipe → use cached RecipeNutrition × servings.
      2. If the log references an Ingredient → compute directly from per-100g data
         treating servings as a multiple of 100 g.
      3. Otherwise → all zeros.

    Returns a dict keyed by NUTRIENT_FIELDS (unrounded Decimals).
    """
    servings = Decimal(str(meal_log.servings))
    zeros = {field: Decimal('0') for field in NUTRIENT_FIELDS}

    if meal_log.recipe_id:
        try:
            nutrition = meal_log.recipe.nutrition
        except Exception:
            return zeros
        return {field: Decimal(str(getattr(nutrition, field, 0))) * servings for field in NUTRIENT_FIELDS}

    if meal_log.ingredient_id:
        # Treat 1 serving = 100 g
        grams = servings * Decimal('100')
        return ingredient_nutrients_for_grams(meal_log.ingredient, grams)

    return zeros


# ---------------------------------------------------------------------------
# Daily totals
# ---------------------------------------------------------------------------

def compute_daily_totals(user: User, date) -> dict:
    """
    Sum all MealLog snapshot nutrients for a user on a given date.
    Returns a dict keyed by NUTRIENT_FIELDS (Decimal).
    """
    from tracker.models import MealLog

    logs = MealLog.objects.filter(user=user, date=date)
    totals = {field: Decimal('0') for field in NUTRIENT_FIELDS}
    for log in logs:
        for field in NUTRIENT_FIELDS:
            totals[field] += Decimal(str(getattr(log, f'snap_{field}', 0)))
    return totals


def compute_daily_totals_by_meal(user: User, date) -> dict:
    """
    Return daily totals split by meal type.
    Returns: {meal_type: {nutrient: Decimal}}
    """
    from tracker.models import MealLog

    logs = MealLog.objects.filter(user=user, date=date)
    by_meal: dict[str, dict] = {}
    for log in logs:
        mt = log.meal_type
        if mt not in by_meal:
            by_meal[mt] = {field: Decimal('0') for field in NUTRIENT_FIELDS}
        for field in NUTRIENT_FIELDS:
            by_meal[mt][field] += Decimal(str(getattr(log, f'snap_{field}', 0)))
    return by_meal


# ---------------------------------------------------------------------------
# Goal management
# ---------------------------------------------------------------------------

@transaction.atomic
def create_default_goals(user: User) -> list:
    """
    Create NutritionGoal rows for all DEFAULT_GOALS for a new user.
    Safe to call multiple times (uses get_or_create).
    Returns list of created/existing NutritionGoal objects.
    """
    goals = []
    for defaults in DEFAULT_GOALS:
        goal, _ = NutritionGoal.objects.get_or_create(
            user=user,
            nutrient=defaults['nutrient'],
            defaults={
                'target_amount': defaults['target_amount'],
                'unit': defaults['unit'],
                'goal_type': defaults['goal_type'],
            },
        )
        goals.append(goal)
    return goals


def get_user_goals(user: User) -> dict:
    """
    Return a dict keyed by nutrient name with goal details.
    Falls back to DEFAULT_GOALS if no goal exists for a nutrient.

    Returns: {nutrient: {'target': Decimal, 'unit': str, 'goal_type': str}}
    """
    db_goals = {g.nutrient: g for g in NutritionGoal.objects.filter(user=user)}
    result = {}

    for defaults in DEFAULT_GOALS:
        nutrient = defaults['nutrient']
        if nutrient in db_goals:
            g = db_goals[nutrient]
            result[nutrient] = {
                'target':    g.target_amount,
                'unit':      g.unit,
                'goal_type': g.goal_type,
            }
        else:
            result[nutrient] = {
                'target':    defaults['target_amount'],
                'unit':      defaults['unit'],
                'goal_type': defaults['goal_type'],
            }
    return result


def validate_goal_bounds(nutrient: str, value: Decimal) -> tuple[bool, str]:
    """
    Check that a goal value is within sensible bounds.
    Returns (is_valid: bool, error_message: str).
    """
    if nutrient not in GOAL_BOUNDS:
        return True, ''
    lo, hi = GOAL_BOUNDS[nutrient]
    if value < lo:
        return False, f"Value {value} is too low (minimum {lo})."
    if value > hi:
        return False, f"Value {value} is too high (maximum {hi})."
    return True, ''


# ---------------------------------------------------------------------------
# Progress calculation
# ---------------------------------------------------------------------------

def compute_progress(totals: dict, goals: dict) -> dict:
    """
    Compare daily totals against goals.

    Returns a dict keyed by nutrient with:
        consumed  – Decimal
        target    – Decimal
        unit      – str
        goal_type – 'minimum' | 'maximum'
        pct       – float  (0–∞, clamped display handled in template)
        status    – 'red' | 'amber' | 'green' | 'blue'
        remaining – Decimal  (how much still needed for minimum goals; 0 for max)
    """
    result = {}
    for nutrient, goal in goals.items():
        consumed  = Decimal(str(totals.get(nutrient, 0)))
        target    = goal['target']
        goal_type = goal['goal_type']
        unit      = goal['unit']

        if target == 0:
            pct = 0.0
        else:
            pct = float(consumed / target) * 100

        if goal_type == 'minimum':
            if pct < 50:
                status = 'red'
            elif pct < 90:
                status = 'amber'
            elif pct <= 110:
                status = 'green'
            else:
                status = 'blue'
            remaining = max(target - consumed, Decimal('0'))
        else:  # maximum – inverted logic
            if pct > 110:
                status = 'red'
            elif pct > 90:
                status = 'amber'
            elif pct <= 90:
                status = 'green'
            else:
                status = 'blue'
            remaining = Decimal('0')

        result[nutrient] = {
            'consumed':  consumed,
            'target':    target,
            'unit':      unit,
            'goal_type': goal_type,
            'pct':       round(min(pct, 200), 1),  # cap at 200 % for bar width
            'status':    status,
            'remaining': remaining,
        }
    return result


def build_summary_sentence(progress: dict) -> str:
    """
    Build a human-readable summary of what the user still needs today.
    E.g. "You still need 18 g protein and 6 mg iron today."
    """
    needed = []
    for nutrient, data in progress.items():
        if data['goal_type'] == 'minimum' and data['remaining'] > 0:
            val = _round_nutrient(data['remaining'], nutrient)
            unit = data['unit']
            label = NutritionGoal.NUTRIENT_CHOICES
            # Get display label
            label_map = dict(NutritionGoal.NUTRIENT_CHOICES)
            display = label_map.get(nutrient, nutrient)
            needed.append(f"{val} {unit} {display.lower()}")

    if not needed:
        return "🎉 You've hit all your nutrient targets for today!"
    if len(needed) == 1:
        return f"You still need {needed[0]} today."
    return f"You still need {', '.join(needed[:-1])} and {needed[-1]} today."

