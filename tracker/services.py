"""
tracker/services.py
-------------------
Business logic for the Meal Tracker, Dashboard, and Recommendations.
No HTTP/request logic here.
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta

from django.contrib.auth.models import User
from django.db.models import Q

from nutrition.services import (
    NUTRIENT_FIELDS,
    PRIMARY_NUTRIENTS,
    compute_log_nutrients,
    compute_daily_totals,
    compute_daily_totals_by_meal,
    compute_progress,
    build_summary_sentence,
    get_user_goals,
)


# ---------------------------------------------------------------------------
# Re-export helpers so views can import from one place
# ---------------------------------------------------------------------------

__all__ = [
    'compute_log_nutrients',
    'compute_daily_totals',
    'compute_daily_totals_by_meal',
    'compute_progress',
    'build_summary_sentence',
    'get_user_goals',
    'log_meal',
    'update_log_servings',
    'copy_log_entry',
    'get_tracker_data',
    'get_dashboard_data',
    'get_seven_day_trend',
    'get_recommendations',
    'guess_next_meal_type',
]


# ---------------------------------------------------------------------------
# Meal log CRUD helpers
# ---------------------------------------------------------------------------

def log_meal(
    user: User,
    date_val: date,
    meal_type: str,
    recipe=None,
    ingredient=None,
    servings: Decimal = Decimal('1'),
    custom_food_name: str = '',
    custom_calories: Decimal | None = None,
) -> 'MealLog':
    """
    Create and save a MealLog entry.
    The MealLog.save() method calls compute_log_nutrients automatically.
    """
    from tracker.models import MealLog

    if recipe is None and ingredient is None and not custom_food_name:
        raise ValueError("Either recipe, ingredient, or custom_food_name must be provided.")

    log = MealLog(
        user=user,
        date=date_val,
        meal_type=meal_type,
        recipe=recipe,
        ingredient=ingredient,
        servings=servings,
        custom_food_name=custom_food_name or '',
        custom_calories=custom_calories,
    )
    log.save()
    return log


def update_log_servings(log, new_servings: Decimal) -> 'MealLog':
    """
    Update the servings on an existing MealLog, recomputing the nutrient snapshot.
    """
    log.servings = Decimal(str(new_servings))
    # snapshot is recomputed in MealLog.save() via _compute_snapshot
    log.save()
    return log


def copy_log_entry(log, target_date: date, target_meal_type: str | None = None) -> 'MealLog':
    """
    Duplicate a MealLog entry to a different date (and optionally a different meal type).
    """
    from tracker.models import MealLog

    new_log = MealLog(
        user=log.user,
        date=target_date,
        meal_type=target_meal_type or log.meal_type,
        recipe=log.recipe,
        ingredient=log.ingredient,
        servings=log.servings,
        custom_food_name=getattr(log, 'custom_food_name', ''),
        custom_calories=getattr(log, 'custom_calories', None),
    )
    new_log.save()
    return new_log


# ---------------------------------------------------------------------------
# Tracker page data
# ---------------------------------------------------------------------------

def get_tracker_data(user: User, date_val: date) -> dict:
    """
    Return all data needed to render the tracker page for one day.

    Returns:
        {
            'logs_by_meal': {meal_type: [MealLog, ...]},
            'totals':       {nutrient: Decimal},
            'goals':        {nutrient: {...}},
            'progress':     {nutrient: {...}},
        }
    """
    from tracker.models import MealLog

    logs = (
        MealLog.objects
        .filter(user=user, date=date_val)
        .select_related('recipe', 'recipe__nutrition', 'ingredient')
        .order_by('meal_type', 'logged_at')
    )

    meal_order = ['breakfast', 'lunch', 'dinner', 'snack']
    logs_by_meal: dict[str, list] = {m: [] for m in meal_order}
    for log in logs:
        mt = log.meal_type
        if mt not in logs_by_meal:
            logs_by_meal[mt] = []
        logs_by_meal[mt].append(log)

    totals  = compute_daily_totals(user, date_val)
    goals   = get_user_goals(user)
    progress = compute_progress(totals, goals)

    return {
        'logs_by_meal': logs_by_meal,
        'totals':       totals,
        'goals':        goals,
        'progress':     progress,
    }


# ---------------------------------------------------------------------------
# Dashboard data
# ---------------------------------------------------------------------------

def get_dashboard_data(user: User, date_val: date) -> dict:
    """
    Return all data needed for the Dashboard page.

    Returns:
        {
            'totals':          {nutrient: Decimal}
            'goals':           {nutrient: {...}}
            'progress':        {nutrient: {...}}
            'summary':         str
            'by_meal':         {meal_type: {nutrient: Decimal}}
            'macro_split':     {'protein': float, 'carbs': float, 'fat': float}  # calories
            'calories_by_meal': {meal_type: float}
        }
    """
    totals   = compute_daily_totals(user, date_val)
    goals    = get_user_goals(user)
    progress = compute_progress(totals, goals)
    summary  = build_summary_sentence(progress)
    by_meal  = compute_daily_totals_by_meal(user, date_val)

    # Macro split (calories from protein, carbs, fat)
    # Protein/carbs = 4 kcal/g, fat = 9 kcal/g
    p_cal = float(totals.get('protein', 0)) * 4
    c_cal = float(totals.get('carbs', 0))   * 4
    f_cal = float(totals.get('fat', 0))     * 9
    total_macro_cal = p_cal + c_cal + f_cal or 1  # avoid /0
    macro_split = {
        'protein': round(p_cal / total_macro_cal * 100, 1),
        'carbs':   round(c_cal / total_macro_cal * 100, 1),
        'fat':     round(f_cal / total_macro_cal * 100, 1),
    }

    meal_order = ['breakfast', 'lunch', 'dinner', 'snack']
    calories_by_meal = {
        m: round(float(by_meal.get(m, {}).get('calories', 0)), 1)
        for m in meal_order
    }

    return {
        'totals':            totals,
        'goals':             goals,
        'progress':          progress,
        'summary':           summary,
        'by_meal':           by_meal,
        'macro_split':       macro_split,
        'calories_by_meal':  calories_by_meal,
    }


# ---------------------------------------------------------------------------
# 7-day trend
# ---------------------------------------------------------------------------

def get_seven_day_trend(user: User, end_date: date) -> dict:
    """
    Return daily totals for each of the 7 days ending on end_date.

    Returns:
        {
            'labels':  ['Mon', 'Tue', ...],        # 7 date labels
            'dates':   ['2025-01-01', ...],
            'data':    {nutrient: [float, ...]}     # 7 values per nutrient
        }
    """
    from tracker.models import MealLog

    days = [end_date - timedelta(days=i) for i in range(6, -1, -1)]

    # Bulk-fetch all logs for the period
    logs = MealLog.objects.filter(
        user=user,
        date__gte=days[0],
        date__lte=days[-1],
    )

    # Group by date
    by_date: dict[date, dict] = {d: {f: Decimal('0') for f in NUTRIENT_FIELDS} for d in days}
    for log in logs:
        if log.date in by_date:
            for field in NUTRIENT_FIELDS:
                by_date[log.date][field] += Decimal(str(getattr(log, f'snap_{field}', 0)))

    labels = [d.strftime('%a') for d in days]
    dates  = [d.isoformat() for d in days]
    data = {
        field: [round(float(by_date[d][field]), 1) for d in days]
        for field in PRIMARY_NUTRIENTS
    }

    return {'labels': labels, 'dates': dates, 'data': data}


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------

def guess_next_meal_type() -> str:
    """Return the most likely next meal type based on current time of day."""
    hour = datetime.now().hour
    if hour < 10:
        return 'breakfast'
    if hour < 14:
        return 'lunch'
    if hour < 18:
        return 'snack'
    return 'dinner'


def score_recipe_for_gaps(recipe, remaining: dict, calorie_limit: float) -> float:
    """
    Score a recipe by how well one serving covers the user's remaining daily needs.

    Algorithm:
    - For each minimum-type nutrient with a gap, compute what fraction of the
      gap one serving covers (capped at 1.0 per nutrient).
    - Weight each contribution by the size of the gap relative to the daily target.
    - Apply a penalty if one serving would push calories over the calorie_limit.
    - Return a score in [0, ∞); higher is better.
    """
    try:
        nutrition = recipe.nutrition
    except Exception:
        return 0.0

    total_weight = 0.0
    weighted_coverage = 0.0

    for nutrient, gap_info in remaining.items():
        if gap_info['goal_type'] != 'minimum':
            continue
        gap = float(gap_info['remaining'])
        target = float(gap_info['target'])
        if target <= 0 or gap <= 0:
            continue

        served = float(getattr(nutrition, nutrient, 0))
        coverage = min(served / gap, 1.0) if gap > 0 else 0.0
        weight = gap / target  # bigger proportional gap → higher weight
        weighted_coverage += coverage * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    score = weighted_coverage / total_weight

    # Calorie penalty: if one serving exceeds remaining calorie budget
    remaining_cal = calorie_limit
    serving_cal = float(getattr(recipe.nutrition, 'calories', 0))
    if remaining_cal > 0 and serving_cal > remaining_cal:
        penalty = min((serving_cal - remaining_cal) / remaining_cal, 1.0)
        score *= (1 - penalty * 0.5)

    return score


def compute_coverage_badge(recipe, remaining: dict) -> str:
    """
    Build a human-friendly badge string, e.g. "Covers 45% of your remaining protein".
    Uses the nutrient with the highest single-nutrient coverage.
    """
    try:
        nutrition = recipe.nutrition
    except Exception:
        return ''

    best_nutrient = None
    best_pct = 0.0

    for nutrient, gap_info in remaining.items():
        if gap_info['goal_type'] != 'minimum':
            continue
        gap = float(gap_info['remaining'])
        if gap <= 0:
            continue
        served = float(getattr(nutrition, nutrient, 0))
        pct = min(served / gap * 100, 100.0)
        if pct > best_pct:
            best_pct = pct
            best_nutrient = nutrient

    if best_nutrient is None or best_pct < 5:
        return ''

    from nutrition.models import NutritionGoal
    label_map = dict(NutritionGoal.NUTRIENT_CHOICES)
    label = label_map.get(best_nutrient, best_nutrient).lower()
    return f"Covers {best_pct:.0f}% of your remaining {label}"


def get_recommendations(
    user: User,
    date_val: date,
    meal_type: str | None = None,
    limit: int = 6,
) -> list:
    """
    Return up to `limit` recommended Recipe objects for the user on date_val.

    Each recipe gets:
        .rec_score   – float
        .rec_badge   – str
        .rec_meal    – str (meal_type filter applied)

    Scoring uses score_recipe_for_gaps, weighted by nutritional gaps.
    Recipes already logged today are excluded.
    """
    from recipes.models import Recipe, RecipeIngredient
    from tracker.models import MealLog
    from django.db.models import Prefetch

    if meal_type is None:
        meal_type = guess_next_meal_type()

    # Daily totals and goals → compute remaining gaps
    totals   = compute_daily_totals(user, date_val)
    goals    = get_user_goals(user)
    progress = compute_progress(totals, goals)

    # Remaining per nutrient (only needed for minimum-type goals with gaps)
    remaining = {
        nutrient: data
        for nutrient, data in progress.items()
        if data['goal_type'] == 'minimum' and data['remaining'] > 0
    }

    calorie_target = float(goals.get('calories', {}).get('target', 2000))
    calorie_consumed = float(totals.get('calories', 0))
    calorie_remaining = max(calorie_target - calorie_consumed, 0)

    # Recipes already logged today
    logged_recipe_ids = set(
        MealLog.objects.filter(user=user, date=date_val, recipe__isnull=False)
        .values_list('recipe_id', flat=True)
    )

    # Candidate recipes: public + user's own, matching meal type or 'any'
    meal_filter = Q(meal_type=meal_type) | Q(meal_type='any')
    candidates = (
        Recipe.objects.filter(Q(is_public=True) | Q(author=user))
        .filter(meal_filter)
        .exclude(id__in=logged_recipe_ids)
        .select_related('nutrition')
        .prefetch_related(
            Prefetch(
                'recipe_ingredients',
                queryset=RecipeIngredient.objects.select_related('ingredient'),
            )
        )
    )

    # Score each candidate
    scored = []
    for recipe in candidates:
        sc = score_recipe_for_gaps(recipe, remaining, calorie_remaining)
        recipe.rec_score = sc
        recipe.rec_badge = compute_coverage_badge(recipe, remaining)
        recipe.rec_meal  = meal_type
        scored.append(recipe)

    # Sort by score descending, take top `limit`
    scored.sort(key=lambda r: r.rec_score, reverse=True)
    return scored[:limit]

