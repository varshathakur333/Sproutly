"""
tracker/views.py
Views for Home, Tracker, Dashboard, and Goals.
"""

import json
from decimal import Decimal
from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_date
from django.contrib import messages

from nutrition.models import NutritionGoal
from nutrition.services import (
    get_user_goals, create_default_goals, compute_progress,
    compute_daily_totals, compute_daily_totals_by_meal, build_summary_sentence,
    DEFAULT_GOALS,
)
from tracker.services import (
    get_tracker_data, get_dashboard_data, get_recommendations,
    get_seven_day_trend, guess_next_meal_type,
)
from accounts.forms import SproutlyPasswordChangeForm
from recipes.models import Recipe


def home(request):
    """
    Home page featuring hero, features, and 6 high-protein recipes.
    """
    featured = (
        Recipe.objects.filter(is_public=True)
        .select_related('nutrition')
        .order_by('-nutrition__protein')[:6]
    )
    return render(request, 'home.html', {
        'featured_recipes': featured,
    })


@login_required
def tracker(request):
    """
    Meal tracker view for logging meals, adjusting portions, and viewing daily totals.
    """
    date_str = request.GET.get('date', date.today().isoformat())
    date_val = parse_date(date_str) or date.today()

    data = get_tracker_data(request.user, date_val)
    logs_by_meal = data.get('logs_by_meal', {})

    meals = {}
    for mt in ['breakfast', 'lunch', 'snack', 'dinner']:
        logs = logs_by_meal.get(mt, [])
        tot_cal = sum(getattr(log, 'snap_calories', 0) for log in logs)
        meals[mt] = {
            'logs': logs,
            'total_calories': tot_cal,
        }

    meal_sections = [
        {'type': 'breakfast', 'title': 'Breakfast', 'color_class': 'tracker-meal-card--breakfast', 'logs': meals['breakfast']['logs'], 'total_calories': meals['breakfast']['total_calories']},
        {'type': 'lunch', 'title': 'Lunch', 'color_class': 'tracker-meal-card--lunch', 'logs': meals['lunch']['logs'], 'total_calories': meals['lunch']['total_calories']},
        {'type': 'snack', 'title': 'Snacks', 'color_class': 'tracker-meal-card--snack', 'logs': meals['snack']['logs'], 'total_calories': meals['snack']['total_calories']},
        {'type': 'dinner', 'title': 'Dinner', 'color_class': 'tracker-meal-card--dinner', 'logs': meals['dinner']['logs'], 'total_calories': meals['dinner']['total_calories']},
    ]

    # Dynamic nudge text based on logged status or nutrient gaps
    if not meals['dinner']['logs']:
        nudge_text = "Dinner is still empty. Want a protein-packed idea?"
    elif not meals['lunch']['logs']:
        nudge_text = "Lunch is still empty. Plant something fresh!"
    elif not meals['breakfast']['logs']:
        nudge_text = "Start your day strong with a high-fiber breakfast!"
    elif not meals['snack']['logs']:
        nudge_text = "Snacks can give you the afternoon boost you need!"
    else:
        nudge_text = "All meals planted for today! Sprig is cheering for you."

    prev_d = (date_val - timedelta(days=1)).isoformat()
    next_d = (date_val + timedelta(days=1)).isoformat()

    context = {
        'current_date': date_val,
        'prev_date': prev_d,
        'next_date': next_d,
        'meals': meals,
        'meal_sections': meal_sections,
        'nudge_text': nudge_text,
        'daily_totals': data.get('totals', {}),
        **data,
    }
    return render(request, 'tracker/tracker.html', context)


@login_required
def dashboard(request):
    """
    Dashboard with progress bars, Chart.js visualizations, and smart recipe recommendations.
    Matches the warm neo-brutalist Sproutly aesthetic from user mockups.
    """
    from tracker.models import MealLog

    real_today = date.today()
    date_str = request.GET.get('date', real_today.isoformat())
    date_val = parse_date(date_str) or real_today
    is_actual_today = (date_val == real_today)

    dash_data = get_dashboard_data(request.user, date_val)
    progress = dash_data.get('progress', {})
    totals = dash_data.get('totals', {})
    goals_data = dash_data.get('goals', {})
    by_meal = dash_data.get('by_meal', {})

    # Label map for nutrients
    label_map = dict(NutritionGoal.NUTRIENT_CHOICES)
    for nut, pdata in progress.items():
        pdata['label'] = label_map.get(nut, nut.title())

    # 1. "Your week" data: 7 days ending on date_val
    week_days = []
    # Fetch all logs in the 7-day window for status calculation
    start_week = date_val - timedelta(days=6)
    week_logs = MealLog.objects.filter(
        user=request.user,
        date__gte=start_week,
        date__lte=date_val,
    )
    cals_by_date = {}
    for wl in week_logs:
        cals_by_date[wl.date] = cals_by_date.get(wl.date, 0) + float(wl.snap_calories)

    for i in range(6, -1, -1):
        d = date_val - timedelta(days=i)
        is_selected = (d == date_val)
        is_real_day = (d == real_today)
        day_cal = cals_by_date.get(d, 0)
        
        if is_selected:
            status = 'today'
        elif day_cal >= 300:
            status = 'hit'
        else:
            status = 'miss'

        name_label = 'Today' if is_real_day else d.strftime('%a')
        week_days.append({
            'name': name_label,
            'day_num': d.day,
            'date_str': d.isoformat(),
            'is_selected': is_selected,
            'is_today': is_real_day,
            'status': status,
        })

    # 2. Calories target & consumed
    cal_target = float(goals_data.get('calories', {}).get('target', 2000))
    cal_consumed = float(totals.get('calories', 0))
    cal_pct = min(round((cal_consumed / cal_target) * 100), 100) if cal_target > 0 else 0

    # 3. Meals today
    today_logs = MealLog.objects.filter(
        user=request.user,
        date=date_val,
    ).select_related('recipe', 'ingredient')

    meal_slots_def = [
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('snack', 'Snacks'),
        ('dinner', 'Dinner'),
    ]
    meals_today = []
    for slot_key, slot_label in meal_slots_def:
        slot_items = [l for l in today_logs if l.meal_type == slot_key]
        if slot_items:
            names = [item.display_name for item in slot_items]
            food_text = ', '.join(names)
            cal_sum = round(sum(float(item.snap_calories) for item in slot_items))
            meals_today.append({
                'key': slot_key,
                'label': slot_label,
                'has_food': True,
                'food_text': food_text,
                'calories': cal_sum,
            })
        else:
            meals_today.append({
                'key': slot_key,
                'label': slot_label,
                'has_food': False,
                'food_text': 'Not planted yet',
                'calories': 0,
            })

    # 4. Micronutrients (Fiber, Iron, Calcium, B12)
    fiber_target = float(goals_data.get('fiber', {}).get('target', 30))
    fiber_consumed = float(totals.get('fiber', 0))
    fiber_pct = min(round((fiber_consumed / fiber_target) * 100), 100) if fiber_target > 0 else 0

    iron_target = float(goals_data.get('iron', {}).get('target', 18))
    iron_consumed = float(totals.get('iron', 0))
    iron_pct = min(round((iron_consumed / iron_target) * 100), 100) if iron_target > 0 else 0

    calcium_target = float(goals_data.get('calcium', {}).get('target', 1000))
    calcium_consumed = float(totals.get('calcium', 0))
    calcium_pct = min(round((calcium_consumed / calcium_target) * 100), 100) if calcium_target > 0 else 0

    b12_target = float(goals_data.get('b12', {}).get('target', 2.4))
    b12_consumed = float(totals.get('b12', 0))
    b12_pct = min(round((b12_consumed / b12_target) * 100), 100) if b12_target > 0 else 0

    micronutrients = [
        {
            'name': 'Fiber',
            'consumed': fiber_consumed,
            'target': fiber_target,
            'unit': 'g',
            'pct': fiber_pct,
            'color': '#F7C548',
        },
        {
            'name': 'Iron',
            'consumed': iron_consumed,
            'target': iron_target,
            'unit': 'mg',
            'pct': iron_pct,
            'color': '#E55B3C',
        },
        {
            'name': 'Calcium',
            'consumed': calcium_consumed,
            'target': calcium_target,
            'unit': 'mg',
            'pct': calcium_pct,
            'color': '#3697A5',
        },
        {
            'name': 'B12',
            'consumed': b12_consumed,
            'target': b12_target,
            'unit': 'µg',
            'pct': b12_pct,
            'color': '#3E6B27',
        },
    ]

    # 5. Macros (Protein, Carbs, Fats)
    protein_target = float(goals_data.get('protein', {}).get('target', 60))
    protein_consumed = float(totals.get('protein', 0))
    protein_pct = min(round((protein_consumed / protein_target) * 100), 100) if protein_target > 0 else 0

    carbs_target = float(goals_data.get('carbs', {}).get('target', 250))
    carbs_consumed = float(totals.get('carbs', 0))
    carbs_pct = min(round((carbs_consumed / carbs_target) * 100), 100) if carbs_target > 0 else 0

    fat_target = float(goals_data.get('fat', {}).get('target', 65))
    fat_consumed = float(totals.get('fat', 0))
    fat_pct = min(round((fat_consumed / fat_target) * 100), 100) if fat_target > 0 else 0

    macro_cards = {
        'protein': {
            'label': 'Protein',
            'consumed': protein_consumed,
            'target': protein_target,
            'pct': protein_pct,
        },
        'carbs': {
            'label': 'Carbs',
            'consumed': carbs_consumed,
            'target': carbs_target,
            'pct': carbs_pct,
        },
        'fats': {
            'label': 'Fats',
            'consumed': fat_consumed,
            'target': fat_target,
            'pct': fat_pct,
        },
    }

    # 6. Sprig Says Advice
    lowest_nut = None
    min_pct = 999
    for nut_k in ['iron', 'protein', 'b12', 'calcium', 'fiber']:
        p_pct = progress.get(nut_k, {}).get('pct', 0)
        if p_pct < min_pct:
            min_pct = p_pct
            lowest_nut = nut_k

    if lowest_nut == 'iron' and min_pct < 80:
        sprig_advice = "You are short on iron. Plant some Palak Tofu at dinner!"
    elif lowest_nut == 'protein' and min_pct < 80:
        sprig_advice = "You are short on protein. Plant some Lentil Dal or Tofu at dinner!"
    elif lowest_nut == 'b12' and min_pct < 80:
        sprig_advice = "You are short on B12. Plant some Fortified Soy Milk or Nutritional Yeast!"
    elif lowest_nut == 'calcium' and min_pct < 80:
        sprig_advice = "You are short on calcium. Plant some Sesame Greens or Tofu at dinner!"
    elif lowest_nut == 'fiber' and min_pct < 80:
        sprig_advice = "You are short on fiber. Plant some Oats or Chia Seed Pudding!"
    elif cal_pct >= 90:
        sprig_advice = "You reached all your targets today! Sprig is blooming with joy! 🌸"
    else:
        sprig_advice = "Keep up the momentum! Plant another nutrient-packed meal today. 🌱"

    # 7. Recommended meal type tab
    req_meal = request.GET.get('meal_type') or guess_next_meal_type()
    raw_recos = get_recommendations(request.user, date_val, meal_type=req_meal, limit=6)

    reco_items = []
    for r in raw_recos:
        cov_pct = 0
        rem_protein = progress.get('protein', {}).get('remaining', 0)
        rec_protein = getattr(getattr(r, 'nutrition', None), 'protein', 0)
        if rem_protein and rem_protein > 0 and rec_protein:
            cov_pct = min(round((float(rec_protein) / float(rem_protein)) * 100), 100)

        r.recipe = r
        r.coverage_pct = cov_pct
        reco_items.append(r)

    # 8. 7-Day Trend Chart
    trend_raw = get_seven_day_trend(request.user, date_val)
    trend_data = {}
    for nut_key, val_list in trend_raw.get('data', {}).items():
        trend_data[nut_key] = {
            'labels': trend_raw.get('labels', []),
            'values': val_list,
        }

    trend_nutrients = {
        'calories': 'Calories',
        'protein': 'Protein',
        'iron': 'Iron',
        'fiber': 'Fiber',
        'calcium': 'Calcium',
        'b12': 'B12',
    }

    meal_types = {
        'breakfast': 'Breakfast',
        'lunch': 'Lunch',
        'dinner': 'Dinner',
        'snack': 'Snack',
    }

    # Macro data in grams for donut chart
    macro_data = {
        'protein': float(totals.get('protein', 0)),
        'carbs': float(totals.get('carbs', 0)),
        'fat': float(totals.get('fat', 0)),
    }

    meal_order = ['breakfast', 'lunch', 'dinner', 'snack']
    meal_labels = ['Breakfast', 'Lunch', 'Dinner', 'Snack']
    meal_values = [float(by_meal.get(m, {}).get('calories', 0)) for m in meal_order]

    context = {
        'today': date_val,
        'date': date_val,
        'real_today': real_today,
        'is_actual_today': is_actual_today,
        'user_greeting': request.user.first_name or 'sprout',
        'week_days': week_days,
        'calories_target': cal_target,
        'calories_consumed': cal_consumed,
        'calories_pct': cal_pct,
        'meals_today': meals_today,
        'micronutrients': micronutrients,
        'macro_cards': macro_cards,
        'sprig_advice': sprig_advice,
        'summary': dash_data.get('summary', ''),
        'progress': progress,
        'macro_data': macro_data,
        'meal_chart_labels': json.dumps(meal_labels),
        'meal_chart_values': json.dumps(meal_values),
        'trend_data': json.dumps(trend_data),
        'trend_nutrients': trend_nutrients,
        'meal_types': meal_types,
        'recommendations': reco_items,
        'selected_meal': req_meal,
    }
    return render(request, 'tracker/dashboard.html', context)


@login_required
def goals(request):
    """
    Goals page: customize nutrient targets and min/max directions,
    or reset to defaults. Also includes inline password change.
    """
    if request.GET.get('reset') == '1' or request.POST.get('action') == 'reset':
        NutritionGoal.objects.filter(user=request.user).delete()
        create_default_goals(request.user)
        messages.success(request, "Goals reset to defaults. 🌱")
        return redirect('goals')

    if request.method == 'POST':
        for defaults in DEFAULT_GOALS:
            nutrient = defaults['nutrient']
            target_val = request.POST.get(f'goal_{nutrient}') or request.POST.get(f'target_{nutrient}')
            type_val = request.POST.get(f'goal_type_{nutrient}') or request.POST.get(f'type_{nutrient}')

            if target_val:
                try:
                    target = Decimal(target_val)
                    goal_type = 'maximum' if type_val in ('max', 'maximum', 'at most') else 'minimum'
                    NutritionGoal.objects.update_or_create(
                        user=request.user,
                        nutrient=nutrient,
                        defaults={
                            'target_amount': target,
                            'unit': defaults['unit'],
                            'goal_type': goal_type,
                        }
                    )
                except Exception:
                    pass

        messages.success(request, "Your growing goals have been saved! 🌱")
        return redirect('goals')

    user_goals = get_user_goals(request.user)
    label_map = dict(NutritionGoal.NUTRIENT_CHOICES)

    goals_context = {}
    for d in DEFAULT_GOALS:
        nut = d['nutrient']
        user_g = user_goals.get(nut)
        target = user_g['target'] if user_g else d['target_amount']
        gt = user_g['goal_type'] if user_g else d['goal_type']
        gt_standard = 'maximum' if gt in ('max', 'maximum', 'at most') else 'minimum'
        gt_short = 'max' if gt_standard == 'maximum' else 'min'

        goals_context[nut] = {
            'label': label_map.get(nut, nut.title()),
            'unit': d['unit'],
            'value': target,
            'default': d['target_amount'],
            'goal_type': gt_standard,
            'goal_type_short': gt_short,
        }

    password_form = SproutlyPasswordChangeForm(user=request.user)

    return render(request, 'tracker/goals.html', {
        'goals': goals_context,
        'password_form': password_form,
    })
