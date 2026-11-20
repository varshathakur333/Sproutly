"""
tracker/tests.py
Tests for recommendation scoring, meal log logic, and permission enforcement.
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from nutrition.models import Ingredient, NutritionGoal
from nutrition.services import (
    create_default_goals, save_recipe_nutrition, compute_daily_totals
)
from recipes.models import Recipe, RecipeIngredient
from tracker.models import MealLog, Favorite
from tracker.services import (
    log_meal,
    update_log_servings,
    copy_log_entry,
    get_recommendations,
    score_recipe_for_gaps,
    compute_coverage_badge,
)


def make_ingredient(name, **kwargs):
    defaults = {
        'category': 'other', 'is_vegan': True,
        'calories': Decimal('200'), 'protein': Decimal('20'),
        'carbs': Decimal('10'), 'fat': Decimal('5'),
        'fiber': Decimal('3'), 'sugar': Decimal('2'),
        'iron': Decimal('3'), 'calcium': Decimal('100'),
        'b12': Decimal('0.5'), 'zinc': Decimal('1'),
        'magnesium': Decimal('30'), 'vitamin_c': Decimal('10'), 'sodium': Decimal('20'),
    }
    defaults.update(kwargs)
    return Ingredient.objects.create(name=name, **defaults)


def make_recipe(title='Dish', servings=1, is_public=True, meal_type='any', user=None):
    r = Recipe.objects.create(
        title=title, servings=servings, is_public=is_public,
        meal_type=meal_type, instructions='Cook.', diet_type='vegan',
        author=user,
    )
    return r


def add_ing(recipe, ing, grams):
    return RecipeIngredient.objects.create(
        recipe=recipe, ingredient=ing, quantity_grams=Decimal(str(grams)),
    )


class MealLogTests(TestCase):
    def setUp(self):
        self.user   = User.objects.create_user('logger', password='pass')
        self.today  = date.today()
        self.ing    = make_ingredient('Protein Food', protein=Decimal('20'))
        self.recipe = make_recipe('Power Bowl')
        add_ing(self.recipe, self.ing, 100)
        save_recipe_nutrition(self.recipe)

    def test_log_meal_creates_entry(self):
        log = log_meal(self.user, self.today, 'lunch', recipe=self.recipe, servings=Decimal('1'))
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.meal_type, 'lunch')

    def test_log_meal_snapshots_nutrients(self):
        log = log_meal(self.user, self.today, 'lunch', recipe=self.recipe, servings=Decimal('1'))
        # 100g ingredient with protein=20 → 20g per serving
        self.assertAlmostEqual(float(log.snap_protein), 20.0, places=1)

    def test_log_meal_scales_with_servings(self):
        log = log_meal(self.user, self.today, 'dinner', recipe=self.recipe, servings=Decimal('2'))
        self.assertAlmostEqual(float(log.snap_protein), 40.0, places=1)

    def test_update_log_servings(self):
        log = log_meal(self.user, self.today, 'lunch', recipe=self.recipe, servings=Decimal('1'))
        updated = update_log_servings(log, Decimal('3'))
        self.assertAlmostEqual(float(updated.snap_protein), 60.0, places=1)

    def test_copy_log_entry(self):
        log  = log_meal(self.user, self.today, 'lunch', recipe=self.recipe, servings=Decimal('1'))
        copy = copy_log_entry(log, self.today.replace(day=self.today.day - 1 if self.today.day > 1 else 1))
        self.assertNotEqual(log.pk, copy.pk)
        self.assertAlmostEqual(float(copy.snap_protein), float(log.snap_protein), places=2)

    def test_log_requires_recipe_or_ingredient(self):
        with self.assertRaises(ValueError):
            log_meal(self.user, self.today, 'snack')

    def test_daily_totals_aggregated(self):
        log_meal(self.user, self.today, 'breakfast', recipe=self.recipe, servings=Decimal('1'))
        log_meal(self.user, self.today, 'lunch',     recipe=self.recipe, servings=Decimal('1'))
        totals = compute_daily_totals(self.user, self.today)
        self.assertAlmostEqual(float(totals['protein']), 40.0, places=1)


class RecommendationTests(TestCase):
    def setUp(self):
        self.user  = User.objects.create_user('recommender', password='pass')
        self.today = date.today()
        create_default_goals(self.user)

        # High-protein ingredient
        self.hp_ing = make_ingredient('High Protein', protein=Decimal('30'),
                                      calories=Decimal('200'), iron=Decimal('5'))
        # High-iron ingredient
        self.hi_ing = make_ingredient('High Iron', protein=Decimal('5'),
                                      calories=Decimal('100'), iron=Decimal('15'))

        self.hp_recipe = make_recipe('HP Dish', servings=1)
        add_ing(self.hp_recipe, self.hp_ing, 100)
        save_recipe_nutrition(self.hp_recipe)

        self.hi_recipe = make_recipe('Iron Dish', servings=1)
        add_ing(self.hi_recipe, self.hi_ing, 100)
        save_recipe_nutrition(self.hi_recipe)

    def test_recommendations_returns_list(self):
        recs = get_recommendations(self.user, self.today)
        self.assertIsInstance(recs, list)

    def test_recommendations_have_score_attribute(self):
        recs = get_recommendations(self.user, self.today)
        for r in recs:
            self.assertTrue(hasattr(r, 'rec_score'))

    def test_recommendations_have_badge_attribute(self):
        recs = get_recommendations(self.user, self.today)
        for r in recs:
            self.assertTrue(hasattr(r, 'rec_badge'))

    def test_recommendation_limit_respected(self):
        recs = get_recommendations(self.user, self.today, limit=2)
        self.assertLessEqual(len(recs), 2)

    def test_score_recipe_for_gaps_positive(self):
        remaining = {
            'protein': {
                'goal_type': 'minimum', 'remaining': Decimal('30'),
                'target': Decimal('60'),
            }
        }
        score = score_recipe_for_gaps(self.hp_recipe, remaining, calorie_limit=1500)
        self.assertGreater(score, 0)

    def test_score_zero_when_no_gaps(self):
        remaining = {}
        score = score_recipe_for_gaps(self.hp_recipe, remaining, calorie_limit=1500)
        self.assertEqual(score, 0.0)

    def test_coverage_badge_non_empty_when_gap_exists(self):
        remaining = {
            'protein': {
                'goal_type': 'minimum', 'remaining': Decimal('30'),
                'target': Decimal('60'),
            }
        }
        badge = compute_coverage_badge(self.hp_recipe, remaining)
        self.assertGreater(len(badge), 0)
        self.assertIn('%', badge)


class DataIsolationTests(TestCase):
    """One user must never access another user's data."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', password='alice123')
        self.bob   = User.objects.create_user('bob',   password='bob12345')
        self.today = date.today()

        self.ing    = make_ingredient('Food')
        self.recipe = make_recipe('Shared Dish', is_public=True)
        add_ing(self.recipe, self.ing, 100)
        save_recipe_nutrition(self.recipe)

        self.alice_log = log_meal(
            self.alice, self.today, 'lunch', recipe=self.recipe, servings=Decimal('1')
        )

    def test_bobs_totals_do_not_include_alices_logs(self):
        totals = compute_daily_totals(self.bob, self.today)
        self.assertEqual(totals['calories'], Decimal('0'))

    def test_bob_cannot_patch_alices_log_via_api(self):
        client = Client()
        client.login(username='bob', password='bob12345')
        url = f'/api/logs/{self.alice_log.pk}/'
        resp = client.patch(url, data='{"servings": "5"}',
                            content_type='application/json')
        # Should be 403 or 404
        self.assertIn(resp.status_code, [403, 404])

    def test_bob_cannot_delete_alices_log_via_api(self):
        client = Client()
        client.login(username='bob', password='bob12345')
        url = f'/api/logs/{self.alice_log.pk}/'
        resp = client.delete(url)
        self.assertIn(resp.status_code, [403, 404])

    def test_alice_private_recipe_invisible_to_bob(self):
        private = make_recipe('Alice Private', is_public=False, user=self.alice)
        from recipes.services import filter_recipes
        qs = filter_recipes({}, user=self.bob)
        self.assertNotIn(private, list(qs))


class DashboardAndGoalsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester', password='tester123')
        create_default_goals(self.user)
        self.client = Client()
        self.client.login(username='tester', password='tester123')

    def test_dashboard_renders_with_mockup_components(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('week_days', resp.context)
        self.assertEqual(len(resp.context['week_days']), 7)
        self.assertIn('meals_today', resp.context)
        self.assertIn('micronutrients', resp.context)
        self.assertIn('macro_cards', resp.context)
        self.assertIn('sprig_advice', resp.context)
        self.assertIn('trend_data', resp.context)
        self.assertIn('recommendations', resp.context)

        # Check rendered HTML contains elements from mockup
        html = resp.content.decode('utf-8')
        self.assertIn('Your week', html)
        self.assertIn('Target ·', html)
        self.assertIn('Meals today', html)
        self.assertIn('Micronutrients', html)
        self.assertIn('Sprig says', html)
        self.assertIn('7-Day Nutrient Trend', html)
        self.assertIn('Recommended for You', html)

    def test_goals_renders_with_dropdown_and_macro_calc(self):
        resp = self.client.get(reverse('goals'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('Your growing goals', html)
        self.assertIn('at least', html)
        self.assertIn('at most', html)
        self.assertIn('Macronutrient', html)
        self.assertIn('Calorie Calculator', html)
        self.assertIn('apply-calc-btn', html)

    def test_goals_post_saves_dropdown_types(self):
        post_data = {
            'goal_calories': '2200',
            'goal_type_calories': 'maximum',
            'goal_protein': '80',
            'goal_type_protein': 'minimum',
        }
        resp = self.client.post(reverse('goals'), data=post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        cal_goal = NutritionGoal.objects.get(user=self.user, nutrient='calories')
        self.assertEqual(cal_goal.target_amount, Decimal('2200'))
        self.assertEqual(cal_goal.goal_type, 'maximum')

        prot_goal = NutritionGoal.objects.get(user=self.user, nutrient='protein')
        self.assertEqual(prot_goal.target_amount, Decimal('80'))
        self.assertEqual(prot_goal.goal_type, 'minimum')


