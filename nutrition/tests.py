"""
nutrition/tests.py
Tests for nutrient calculation, goal management, and service functions.
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User

from nutrition.models import Ingredient, NutritionGoal
from nutrition.services import (
    ingredient_nutrients_for_grams,
    compute_recipe_nutrition,
    save_recipe_nutrition,
    compute_daily_totals,
    create_default_goals,
    get_user_goals,
    validate_goal_bounds,
    compute_progress,
    build_summary_sentence,
    DEFAULT_GOALS,
    NUTRIENT_FIELDS,
)
from recipes.models import Recipe, RecipeIngredient, RecipeNutrition


def make_ingredient(**kwargs):
    defaults = {
        'name': 'Test Ingredient',
        'category': 'other',
        'is_vegan': True,
        'calories': Decimal('100'),
        'protein':  Decimal('10'),
        'carbs':    Decimal('20'),
        'fat':      Decimal('5'),
        'fiber':    Decimal('3'),
        'sugar':    Decimal('2'),
        'iron':     Decimal('1'),
        'calcium':  Decimal('50'),
        'b12':      Decimal('0'),
        'zinc':     Decimal('1'),
        'magnesium': Decimal('10'),
        'vitamin_c': Decimal('5'),
        'sodium':   Decimal('10'),
    }
    defaults.update(kwargs)
    return Ingredient.objects.create(**defaults)


class IngredientNutrientCalculationTests(TestCase):
    def setUp(self):
        self.ing = make_ingredient(
            name='Rice',
            calories=Decimal('130'), protein=Decimal('2.7'),
            carbs=Decimal('28'), fat=Decimal('0.3'),
        )

    def test_full_100g_matches_ingredient(self):
        result = ingredient_nutrients_for_grams(self.ing, Decimal('100'))
        self.assertEqual(result['calories'], Decimal('130'))
        self.assertEqual(result['protein'],  Decimal('2.7'))

    def test_half_portion(self):
        result = ingredient_nutrients_for_grams(self.ing, Decimal('50'))
        self.assertAlmostEqual(float(result['calories']), 65.0, places=2)
        self.assertAlmostEqual(float(result['protein']),  1.35, places=2)

    def test_zero_grams(self):
        result = ingredient_nutrients_for_grams(self.ing, Decimal('0'))
        for field in NUTRIENT_FIELDS:
            self.assertEqual(result[field], Decimal('0'))

    def test_all_nutrient_fields_present(self):
        result = ingredient_nutrients_for_grams(self.ing, Decimal('100'))
        for field in NUTRIENT_FIELDS:
            self.assertIn(field, result)


class RecipeNutritionCalculationTests(TestCase):
    def setUp(self):
        self.user   = User.objects.create_user('chef', password='pass')
        self.lentil = make_ingredient(
            name='Lentils',
            calories=Decimal('116'), protein=Decimal('9'),
            carbs=Decimal('20'), fat=Decimal('0.4'),
            fiber=Decimal('7.9'), iron=Decimal('3.3'),
            calcium=Decimal('19'), b12=Decimal('0'),
        )
        self.spinach = make_ingredient(
            name='Spinach',
            calories=Decimal('23'), protein=Decimal('2.9'),
            carbs=Decimal('3.6'), fat=Decimal('0.4'),
            fiber=Decimal('2.2'), iron=Decimal('2.7'),
            calcium=Decimal('99'), b12=Decimal('0'),
        )
        self.recipe = Recipe.objects.create(
            author=self.user,
            title='Lentil Soup',
            instructions='Cook.',
            servings=4,
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=self.lentil,
            quantity_grams=Decimal('200'),
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=self.spinach,
            quantity_grams=Decimal('100'),
        )

    def test_per_serving_calories(self):
        # Total calories = 200/100*116 + 100/100*23 = 232 + 23 = 255
        # Per serving (4) = 63.75
        result = compute_recipe_nutrition(self.recipe)
        self.assertAlmostEqual(float(result['calories']), 63.75, places=2)

    def test_per_serving_protein(self):
        # 200/100*9 + 100/100*2.9 = 18 + 2.9 = 20.9  / 4 = 5.225
        result = compute_recipe_nutrition(self.recipe)
        self.assertAlmostEqual(float(result['protein']), 5.225, places=3)

    def test_per_serving_iron(self):
        # 200/100*3.3 + 100/100*2.7 = 6.6 + 2.7 = 9.3 / 4 = 2.325
        result = compute_recipe_nutrition(self.recipe)
        self.assertAlmostEqual(float(result['iron']), 2.325, places=3)

    def test_save_recipe_nutrition_creates_row(self):
        nutrition = save_recipe_nutrition(self.recipe)
        self.assertIsInstance(nutrition, RecipeNutrition)
        self.assertAlmostEqual(float(nutrition.calories), 63.75, places=2)

    def test_save_recipe_nutrition_manual_override(self):
        manual = {f: Decimal('99') for f in NUTRIENT_FIELDS}
        nutrition = save_recipe_nutrition(self.recipe, manual_data=manual)
        self.assertTrue(nutrition.is_manual)
        self.assertEqual(float(nutrition.calories), 99.0)

    def test_single_serving_recipe(self):
        self.recipe.servings = 1
        self.recipe.save()
        result = compute_recipe_nutrition(self.recipe)
        # 200/100*116 + 100/100*23 = 255
        self.assertAlmostEqual(float(result['calories']), 255.0, places=2)

    def test_all_fields_returned(self):
        result = compute_recipe_nutrition(self.recipe)
        for field in NUTRIENT_FIELDS:
            self.assertIn(field, result)


class GoalManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('goalie', password='pass')

    def test_create_default_goals_creates_all(self):
        goals = create_default_goals(self.user)
        self.assertEqual(len(goals), len(DEFAULT_GOALS))

    def test_create_default_goals_idempotent(self):
        create_default_goals(self.user)
        create_default_goals(self.user)
        count = NutritionGoal.objects.filter(user=self.user).count()
        self.assertEqual(count, len(DEFAULT_GOALS))

    def test_get_user_goals_returns_all_nutrients(self):
        create_default_goals(self.user)
        goals = get_user_goals(self.user)
        for defaults in DEFAULT_GOALS:
            self.assertIn(defaults['nutrient'], goals)

    def test_validate_goal_bounds_valid(self):
        ok, msg = validate_goal_bounds('protein', Decimal('60'))
        self.assertTrue(ok)
        self.assertEqual(msg, '')

    def test_validate_goal_bounds_too_low(self):
        ok, msg = validate_goal_bounds('protein', Decimal('1'))
        self.assertFalse(ok)

    def test_validate_goal_bounds_too_high(self):
        ok, msg = validate_goal_bounds('calcium', Decimal('99999'))
        self.assertFalse(ok)

    def test_validate_unknown_nutrient_always_valid(self):
        ok, _ = validate_goal_bounds('unknown_nutrient', Decimal('9999'))
        self.assertTrue(ok)


class ProgressCalculationTests(TestCase):
    def setUp(self):
        self.goals = {
            'calories': {'target': Decimal('2000'), 'unit': 'kcal', 'goal_type': 'minimum'},
            'protein':  {'target': Decimal('60'),   'unit': 'g',    'goal_type': 'minimum'},
            'fat':      {'target': Decimal('65'),   'unit': 'g',    'goal_type': 'maximum'},
        }

    def test_zero_consumed_gives_red_status(self):
        totals   = {k: Decimal('0') for k in NUTRIENT_FIELDS}
        progress = compute_progress(totals, self.goals)
        self.assertEqual(progress['calories']['status'], 'red')
        self.assertEqual(progress['protein']['status'],  'red')

    def test_full_target_gives_green(self):
        totals = {'calories': Decimal('2000'), 'protein': Decimal('60'), 'fat': Decimal('65')}
        progress = compute_progress(totals, self.goals)
        self.assertEqual(progress['calories']['status'], 'green')

    def test_over_target_minimum_gives_blue(self):
        totals = {'calories': Decimal('2500'), 'protein': Decimal('80'), 'fat': Decimal('30')}
        progress = compute_progress(totals, self.goals)
        self.assertEqual(progress['calories']['status'], 'blue')

    def test_maximum_goal_over_limit_is_red(self):
        totals = {'calories': Decimal('0'), 'protein': Decimal('0'), 'fat': Decimal('80')}
        progress = compute_progress(totals, self.goals)
        self.assertEqual(progress['fat']['status'], 'red')

    def test_pct_capped_at_200(self):
        totals = {'calories': Decimal('10000'), 'protein': Decimal('0'), 'fat': Decimal('0')}
        progress = compute_progress(totals, self.goals)
        self.assertLessEqual(progress['calories']['pct'], 200.0)

    def test_remaining_is_zero_for_max_goal(self):
        totals = {'calories': Decimal('0'), 'protein': Decimal('0'), 'fat': Decimal('50')}
        progress = compute_progress(totals, self.goals)
        self.assertEqual(progress['fat']['remaining'], Decimal('0'))


class SummaryTests(TestCase):
    def test_all_met_gives_celebration(self):
        progress = {
            'protein': {
                'goal_type': 'minimum', 'remaining': Decimal('0'),
                'unit': 'g',
            }
        }
        msg = build_summary_sentence(progress)
        self.assertIn('🎉', msg)

    def test_unmet_goal_appears_in_message(self):
        progress = {
            'protein': {
                'goal_type': 'minimum', 'remaining': Decimal('20'),
                'unit': 'g',
            }
        }
        msg = build_summary_sentence(progress)
        self.assertIn('protein', msg.lower())
        self.assertIn('20', msg)


class DailyTotalsTests(TestCase):
    def setUp(self):
        from datetime import date
        self.user = User.objects.create_user('tracker_test', password='pass')
        self.today = date.today()

        # Create ingredient and recipe
        self.ing = make_ingredient(
            name='Test Food', calories=Decimal('200'), protein=Decimal('20'),
            carbs=Decimal('10'), fat=Decimal('5'), iron=Decimal('2'),
            calcium=Decimal('100'), b12=Decimal('0.5'),
        )
        self.recipe = Recipe.objects.create(
            title='Test Recipe', instructions='Cook.', servings=1, is_public=True,
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=self.ing, quantity_grams=Decimal('100'),
        )
        save_recipe_nutrition(self.recipe)

    def test_daily_totals_sums_logs(self):
        from tracker.models import MealLog
        MealLog.objects.create(
            user=self.user, date=self.today, meal_type='lunch',
            recipe=self.recipe, servings=Decimal('2'),
        )
        totals = compute_daily_totals(self.user, self.today)
        # recipe is 1 serving = 200 cal, × 2 servings = 400 cal
        self.assertAlmostEqual(float(totals['calories']), 400.0, places=1)

    def test_daily_totals_empty_gives_zeros(self):
        totals = compute_daily_totals(self.user, self.today)
        self.assertEqual(totals['calories'], Decimal('0'))

