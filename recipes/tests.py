"""
recipes/tests.py
Tests for recipe filtering, permission logic, and ingredient match scoring.
"""

from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User

from nutrition.models import Ingredient
from recipes.models import Recipe, RecipeIngredient, RecipeNutrition
from recipes.services import (
    filter_recipes,
    sort_recipes,
    compute_ingredient_match,
    annotate_match_data,
)
from nutrition.services import save_recipe_nutrition


def make_ingredient(name, **kwargs):
    defaults = {
        'category': 'other', 'is_vegan': True,
        'calories': Decimal('100'), 'protein': Decimal('10'),
        'carbs': Decimal('20'), 'fat': Decimal('5'),
        'fiber': Decimal('3'), 'sugar': Decimal('2'),
        'iron': Decimal('1'), 'calcium': Decimal('50'),
        'b12': Decimal('0'), 'zinc': Decimal('1'),
        'magnesium': Decimal('10'), 'vitamin_c': Decimal('5'), 'sodium': Decimal('10'),
    }
    defaults.update(kwargs)
    return Ingredient.objects.create(name=name, **defaults)


def make_recipe(user=None, title='Test', diet='vegan', meal='lunch', servings=2,
                is_public=True, **kwargs):
    return Recipe.objects.create(
        author=user, title=title, diet_type=diet, meal_type=meal,
        servings=servings, is_public=is_public, instructions='Cook.',
        **kwargs
    )


def add_ingredient(recipe, ingredient, grams):
    return RecipeIngredient.objects.create(
        recipe=recipe, ingredient=ingredient, quantity_grams=Decimal(str(grams))
    )


class RecipeFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('cook', password='pass')

        self.lentil = make_ingredient('Lentils', protein=Decimal('9'), iron=Decimal('3'))
        self.tofu   = make_ingredient('Tofu',   protein=Decimal('8'), iron=Decimal('1.5'))
        self.salt   = make_ingredient('Salt', is_staple=True, category='spice',
                                      protein=Decimal('0'), iron=Decimal('0'))

        self.r1 = make_recipe(title='Dal Soup', diet='vegan', meal='lunch')
        add_ingredient(self.r1, self.lentil, 200)
        add_ingredient(self.r1, self.salt, 5)
        save_recipe_nutrition(self.r1)

        self.r2 = make_recipe(title='Tofu Scramble', diet='vegan', meal='breakfast')
        add_ingredient(self.r2, self.tofu, 300)
        save_recipe_nutrition(self.r2)

        self.r3 = make_recipe(title='Paneer Dish', diet='vegetarian', meal='dinner',
                              is_public=False, user=self.user)
        add_ingredient(self.r3, self.lentil, 100)
        save_recipe_nutrition(self.r3)

    def test_public_only_for_anonymous(self):
        qs = filter_recipes({}, user=None)
        titles = list(qs.values_list('title', flat=True))
        self.assertIn('Dal Soup', titles)
        self.assertNotIn('Paneer Dish', titles)

    def test_authenticated_sees_own_private(self):
        qs = filter_recipes({}, user=self.user)
        titles = list(qs.values_list('title', flat=True))
        self.assertIn('Paneer Dish', titles)

    def test_diet_type_filter(self):
        qs = filter_recipes({'diet_type': 'vegetarian'}, user=self.user)
        for recipe in qs:
            self.assertEqual(recipe.diet_type, 'vegetarian')

    def test_meal_type_filter(self):
        qs = filter_recipes({'meal_type': 'breakfast'}, user=None)
        for recipe in qs:
            self.assertEqual(recipe.meal_type, 'breakfast')

    def test_text_search_by_title(self):
        qs = filter_recipes({'q': 'tofu'}, user=None)
        titles = list(qs.values_list('title', flat=True))
        self.assertIn('Tofu Scramble', titles)
        self.assertNotIn('Dal Soup', titles)

    def test_text_search_by_ingredient(self):
        qs = filter_recipes({'q': 'lentil'}, user=None)
        titles = list(qs.values_list('title', flat=True))
        self.assertIn('Dal Soup', titles)

    def test_protein_min_filter(self):
        # r1 (Dal Soup): 200g lentils → 200/100*9 / 2 servings = 9 g protein per serving
        # r2 (Tofu): 300/100*8 / 2 = 12 g protein per serving
        qs = filter_recipes({'protein_min': '10'}, user=None)
        titles = list(qs.values_list('title', flat=True))
        self.assertIn('Tofu Scramble', titles)
        self.assertNotIn('Dal Soup', titles)

    def test_iron_min_filter(self):
        # r1: 200/100*3 / 2 = 3 mg iron per serving
        qs = filter_recipes({'iron_min': '2.5'}, user=None)
        titles = list(qs.values_list('title', flat=True))
        self.assertIn('Dal Soup', titles)
        self.assertNotIn('Tofu Scramble', titles)

    def test_combined_protein_and_iron_filter(self):
        # Protein >= 20 AND iron >= 4 → neither recipe qualifies
        qs = filter_recipes({'protein_min': '20', 'iron_min': '4'}, user=None)
        self.assertEqual(qs.count(), 0)

    def test_must_include_filter(self):
        qs = filter_recipes({'must_include': str(self.tofu.id)}, user=None)
        for r in qs:
            ids = list(r.recipe_ingredients.values_list('ingredient_id', flat=True))
            self.assertIn(self.tofu.id, ids)

    def test_must_exclude_filter(self):
        qs = filter_recipes({'must_exclude': str(self.tofu.id)}, user=None)
        for r in qs:
            ids = list(r.recipe_ingredients.values_list('ingredient_id', flat=True))
            self.assertNotIn(self.tofu.id, ids)

    def test_preset_high_protein(self):
        # Preset 'high_protein' sets protein_min=15
        qs = filter_recipes({'preset': 'high_protein'}, user=None)
        # Tofu scramble has 12 g/serving → shouldn't appear
        # Neither should dal (9 g)
        self.assertEqual(qs.count(), 0)

    def test_sort_protein_desc(self):
        result = sort_recipes(filter_recipes({}, user=None), 'protein_desc')
        proteins = [float(r.nutrition.protein) for r in result]
        self.assertEqual(proteins, sorted(proteins, reverse=True))


class IngredientMatchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('matcher', password='pass')

        self.lentil  = make_ingredient('Lentils2')
        self.spinach = make_ingredient('Spinach2')
        self.salt    = make_ingredient('Salt2', category='spice', is_staple=True)

        self.recipe = make_recipe(title='Match Recipe', servings=1)
        add_ingredient(self.recipe, self.lentil,  150)
        add_ingredient(self.recipe, self.spinach, 100)
        add_ingredient(self.recipe, self.salt,    5)   # staple – excluded from count

    def test_full_match_score_is_one(self):
        have = {self.lentil.id, self.spinach.id}
        result = compute_ingredient_match(self.recipe, have)
        self.assertAlmostEqual(result['score'], 1.0)
        self.assertEqual(result['missing'], [])
        self.assertEqual(result['total'], 2)  # salt excluded

    def test_half_match_score(self):
        have = {self.lentil.id}
        result = compute_ingredient_match(self.recipe, have)
        self.assertAlmostEqual(result['score'], 0.5)
        self.assertIn('Spinach2', result['missing'])

    def test_zero_match_score(self):
        result = compute_ingredient_match(self.recipe, set())
        self.assertAlmostEqual(result['score'], 0.0)
        self.assertEqual(len(result['missing']), 2)

    def test_staple_not_counted_in_total(self):
        result = compute_ingredient_match(self.recipe, set())
        self.assertEqual(result['total'], 2)  # lentil + spinach, not salt


class PermissionTests(TestCase):
    def setUp(self):
        self.owner  = User.objects.create_user('owner',  password='pass')
        self.other  = User.objects.create_user('other',  password='pass')
        self.recipe = make_recipe(user=self.owner, title='Private', is_public=False)

    def test_owner_can_see_private_recipe(self):
        qs = filter_recipes({'tab': 'mine'}, user=self.owner)
        self.assertIn(self.recipe, list(qs))

    def test_other_user_cannot_see_private_recipe(self):
        qs = filter_recipes({}, user=self.other)
        self.assertNotIn(self.recipe, list(qs))

    def test_anonymous_cannot_see_private_recipe(self):
        qs = filter_recipes({}, user=None)
        self.assertNotIn(self.recipe, list(qs))

