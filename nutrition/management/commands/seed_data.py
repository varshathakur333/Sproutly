"""
nutrition/management/commands/seed_data.py
------------------------------------------
Populates the database with:
  - 60+ common vegetarian/vegan ingredients with accurate nutrient values
  - 25+ recipes across all meal types (Indian staples + international)
  - A demo user (demo / demo12345) with default goals + 3 days of logs

Run: python manage.py seed_data
Idempotent: safe to run multiple times.
"""

from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from nutrition.models import Ingredient, NutritionGoal
from nutrition.services import create_default_goals, save_recipe_nutrition
from recipes.models import Recipe, RecipeIngredient, RecipeNutrition
from tracker.models import MealLog, Favorite
from tracker.services import log_meal


# ---------------------------------------------------------------------------
# Ingredient data  (nutrients per 100 g)
# ---------------------------------------------------------------------------

INGREDIENTS = [
    # --- Legumes ---
    {
        'name': 'Red Lentils (Masoor Dal)', 'category': 'legume', 'is_vegan': True,
        'calories': Decimal('116'), 'protein': Decimal('9.0'), 'carbs': Decimal('20.1'),
        'fat': Decimal('0.4'), 'fiber': Decimal('7.9'), 'sugar': Decimal('1.8'),
        'iron': Decimal('3.3'), 'calcium': Decimal('19'), 'b12': Decimal('0'),
        'zinc': Decimal('1.2'), 'magnesium': Decimal('36'), 'vitamin_c': Decimal('1.5'), 'sodium': Decimal('2'),
    },
    {
        'name': 'Green Lentils', 'category': 'legume', 'is_vegan': True,
        'calories': Decimal('116'), 'protein': Decimal('9.0'), 'carbs': Decimal('20.1'),
        'fat': Decimal('0.4'), 'fiber': Decimal('7.9'), 'sugar': Decimal('1.8'),
        'iron': Decimal('3.3'), 'calcium': Decimal('19'), 'b12': Decimal('0'),
        'zinc': Decimal('1.3'), 'magnesium': Decimal('36'), 'vitamin_c': Decimal('1.5'), 'sodium': Decimal('2'),
    },
    {
        'name': 'Chickpeas (Chana)', 'category': 'legume', 'is_vegan': True,
        'calories': Decimal('164'), 'protein': Decimal('8.9'), 'carbs': Decimal('27.4'),
        'fat': Decimal('2.6'), 'fiber': Decimal('7.6'), 'sugar': Decimal('4.8'),
        'iron': Decimal('2.9'), 'calcium': Decimal('49'), 'b12': Decimal('0'),
        'zinc': Decimal('1.5'), 'magnesium': Decimal('48'), 'vitamin_c': Decimal('1.3'), 'sodium': Decimal('7'),
    },
    {
        'name': 'Black-Eyed Peas (Lobia)', 'category': 'legume', 'is_vegan': True,
        'calories': Decimal('116'), 'protein': Decimal('7.7'), 'carbs': Decimal('20.8'),
        'fat': Decimal('0.5'), 'fiber': Decimal('6.5'), 'sugar': Decimal('3.3'),
        'iron': Decimal('2.5'), 'calcium': Decimal('24'), 'b12': Decimal('0'),
        'zinc': Decimal('1.3'), 'magnesium': Decimal('53'), 'vitamin_c': Decimal('0.4'), 'sodium': Decimal('4'),
    },
    {
        'name': 'Kidney Beans (Rajma)', 'category': 'legume', 'is_vegan': True,
        'calories': Decimal('127'), 'protein': Decimal('8.7'), 'carbs': Decimal('22.8'),
        'fat': Decimal('0.5'), 'fiber': Decimal('7.4'), 'sugar': Decimal('0.3'),
        'iron': Decimal('2.9'), 'calcium': Decimal('50'), 'b12': Decimal('0'),
        'zinc': Decimal('1.4'), 'magnesium': Decimal('45'), 'vitamin_c': Decimal('1.4'), 'sodium': Decimal('2'),
    },
    {
        'name': 'Moong Dal (Split Mung Beans)', 'category': 'legume', 'is_vegan': True,
        'calories': Decimal('105'), 'protein': Decimal('7.0'), 'carbs': Decimal('19.2'),
        'fat': Decimal('0.4'), 'fiber': Decimal('7.6'), 'sugar': Decimal('2.0'),
        'iron': Decimal('1.8'), 'calcium': Decimal('27'), 'b12': Decimal('0'),
        'zinc': Decimal('0.8'), 'magnesium': Decimal('37'), 'vitamin_c': Decimal('1.0'), 'sodium': Decimal('2'),
    },
    {
        'name': 'Toor Dal (Pigeon Peas)', 'category': 'legume', 'is_vegan': True,
        'calories': Decimal('343'), 'protein': Decimal('22.3'), 'carbs': Decimal('57.6'),
        'fat': Decimal('1.5'), 'fiber': Decimal('15.0'), 'sugar': Decimal('6.0'),
        'iron': Decimal('5.2'), 'calcium': Decimal('130'), 'b12': Decimal('0'),
        'zinc': Decimal('2.8'), 'magnesium': Decimal('183'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('17'),
    },
    # --- Grains ---
    {
        'name': 'Brown Rice', 'category': 'grain', 'is_vegan': True,
        'calories': Decimal('216'), 'protein': Decimal('5.0'), 'carbs': Decimal('45.0'),
        'fat': Decimal('1.8'), 'fiber': Decimal('3.5'), 'sugar': Decimal('0.7'),
        'iron': Decimal('1.0'), 'calcium': Decimal('10'), 'b12': Decimal('0'),
        'zinc': Decimal('1.2'), 'magnesium': Decimal('84'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('1'),
    },
    {
        'name': 'Basmati Rice', 'category': 'grain', 'is_vegan': True,
        'calories': Decimal('130'), 'protein': Decimal('2.7'), 'carbs': Decimal('28.0'),
        'fat': Decimal('0.3'), 'fiber': Decimal('0.4'), 'sugar': Decimal('0'),
        'iron': Decimal('0.2'), 'calcium': Decimal('10'), 'b12': Decimal('0'),
        'zinc': Decimal('0.5'), 'magnesium': Decimal('12'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('0'),
    },
    {
        'name': 'Rolled Oats', 'category': 'grain', 'is_vegan': True,
        'calories': Decimal('389'), 'protein': Decimal('16.9'), 'carbs': Decimal('66.3'),
        'fat': Decimal('6.9'), 'fiber': Decimal('10.6'), 'sugar': Decimal('0'),
        'iron': Decimal('4.7'), 'calcium': Decimal('54'), 'b12': Decimal('0'),
        'zinc': Decimal('3.6'), 'magnesium': Decimal('177'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('2'),
    },
    {
        'name': 'Quinoa', 'category': 'grain', 'is_vegan': True,
        'calories': Decimal('120'), 'protein': Decimal('4.4'), 'carbs': Decimal('21.3'),
        'fat': Decimal('1.9'), 'fiber': Decimal('2.8'), 'sugar': Decimal('0.9'),
        'iron': Decimal('1.5'), 'calcium': Decimal('17'), 'b12': Decimal('0'),
        'zinc': Decimal('1.1'), 'magnesium': Decimal('64'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('7'),
    },
    {
        'name': 'Whole Wheat Flour (Atta)', 'category': 'grain', 'is_vegan': True,
        'calories': Decimal('340'), 'protein': Decimal('13.2'), 'carbs': Decimal('72.0'),
        'fat': Decimal('2.5'), 'fiber': Decimal('10.7'), 'sugar': Decimal('0.4'),
        'iron': Decimal('3.6'), 'calcium': Decimal('34'), 'b12': Decimal('0'),
        'zinc': Decimal('2.6'), 'magnesium': Decimal('138'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('2'),
    },
    {
        'name': 'Semolina (Sooji)', 'category': 'grain', 'is_vegan': True,
        'calories': Decimal('360'), 'protein': Decimal('12.7'), 'carbs': Decimal('72.8'),
        'fat': Decimal('1.1'), 'fiber': Decimal('3.9'), 'sugar': Decimal('0'),
        'iron': Decimal('1.2'), 'calcium': Decimal('17'), 'b12': Decimal('0'),
        'zinc': Decimal('1.0'), 'magnesium': Decimal('47'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('1'),
    },
    # --- Protein-rich plant foods ---
    {
        'name': 'Tofu (Firm)', 'category': 'other', 'is_vegan': True,
        'calories': Decimal('76'), 'protein': Decimal('8.1'), 'carbs': Decimal('1.9'),
        'fat': Decimal('4.2'), 'fiber': Decimal('0.3'), 'sugar': Decimal('0.5'),
        'iron': Decimal('1.6'), 'calcium': Decimal('350'), 'b12': Decimal('0'),
        'zinc': Decimal('0.8'), 'magnesium': Decimal('30'), 'vitamin_c': Decimal('0.1'), 'sodium': Decimal('7'),
    },
    {
        'name': 'Tempeh', 'category': 'other', 'is_vegan': True,
        'calories': Decimal('193'), 'protein': Decimal('20.3'), 'carbs': Decimal('7.6'),
        'fat': Decimal('10.8'), 'fiber': Decimal('0'), 'sugar': Decimal('0'),
        'iron': Decimal('2.7'), 'calcium': Decimal('111'), 'b12': Decimal('0'),
        'zinc': Decimal('1.7'), 'magnesium': Decimal('81'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('9'),
    },
    # --- Dairy ---
    {
        'name': 'Paneer (Indian Cottage Cheese)', 'category': 'dairy', 'is_vegan': False,
        'calories': Decimal('265'), 'protein': Decimal('18.3'), 'carbs': Decimal('1.2'),
        'fat': Decimal('20.8'), 'fiber': Decimal('0'), 'sugar': Decimal('1.2'),
        'iron': Decimal('0.5'), 'calcium': Decimal('480'), 'b12': Decimal('0.8'),
        'zinc': Decimal('2.6'), 'magnesium': Decimal('8'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('30'),
    },
    {
        'name': 'Whole Milk', 'category': 'dairy', 'is_vegan': False,
        'calories': Decimal('61'), 'protein': Decimal('3.2'), 'carbs': Decimal('4.8'),
        'fat': Decimal('3.3'), 'fiber': Decimal('0'), 'sugar': Decimal('5.1'),
        'iron': Decimal('0.0'), 'calcium': Decimal('113'), 'b12': Decimal('0.45'),
        'zinc': Decimal('0.4'), 'magnesium': Decimal('10'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('43'),
    },
    {
        'name': 'Greek Yogurt (Full-fat)', 'category': 'dairy', 'is_vegan': False,
        'calories': Decimal('97'), 'protein': Decimal('9.0'), 'carbs': Decimal('3.6'),
        'fat': Decimal('5.0'), 'fiber': Decimal('0'), 'sugar': Decimal('3.2'),
        'iron': Decimal('0.1'), 'calcium': Decimal('110'), 'b12': Decimal('0.75'),
        'zinc': Decimal('0.5'), 'magnesium': Decimal('11'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('36'),
    },
    {
        'name': 'Curd / Plain Yogurt', 'category': 'dairy', 'is_vegan': False,
        'calories': Decimal('61'), 'protein': Decimal('3.5'), 'carbs': Decimal('4.7'),
        'fat': Decimal('3.3'), 'fiber': Decimal('0'), 'sugar': Decimal('4.7'),
        'iron': Decimal('0.1'), 'calcium': Decimal('121'), 'b12': Decimal('0.37'),
        'zinc': Decimal('0.6'), 'magnesium': Decimal('12'), 'vitamin_c': Decimal('0.5'), 'sodium': Decimal('46'),
    },
    {
        'name': 'Ghee (Clarified Butter)', 'category': 'dairy', 'is_vegan': False,
        'calories': Decimal('900'), 'protein': Decimal('0'), 'carbs': Decimal('0'),
        'fat': Decimal('99.5'), 'fiber': Decimal('0'), 'sugar': Decimal('0'),
        'iron': Decimal('0'), 'calcium': Decimal('4'), 'b12': Decimal('0'),
        'zinc': Decimal('0.1'), 'magnesium': Decimal('0'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('2'),
    },
    # --- Vegetables ---
    {
        'name': 'Spinach (Palak)', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('23'), 'protein': Decimal('2.9'), 'carbs': Decimal('3.6'),
        'fat': Decimal('0.4'), 'fiber': Decimal('2.2'), 'sugar': Decimal('0.4'),
        'iron': Decimal('2.7'), 'calcium': Decimal('99'), 'b12': Decimal('0'),
        'zinc': Decimal('0.5'), 'magnesium': Decimal('79'), 'vitamin_c': Decimal('28'), 'sodium': Decimal('79'),
    },
    {
        'name': 'Tomato', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('18'), 'protein': Decimal('0.9'), 'carbs': Decimal('3.9'),
        'fat': Decimal('0.2'), 'fiber': Decimal('1.2'), 'sugar': Decimal('2.6'),
        'iron': Decimal('0.3'), 'calcium': Decimal('10'), 'b12': Decimal('0'),
        'zinc': Decimal('0.2'), 'magnesium': Decimal('11'), 'vitamin_c': Decimal('14'), 'sodium': Decimal('5'),
    },
    {
        'name': 'Onion', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('40'), 'protein': Decimal('1.1'), 'carbs': Decimal('9.3'),
        'fat': Decimal('0.1'), 'fiber': Decimal('1.7'), 'sugar': Decimal('4.2'),
        'iron': Decimal('0.2'), 'calcium': Decimal('23'), 'b12': Decimal('0'),
        'zinc': Decimal('0.2'), 'magnesium': Decimal('10'), 'vitamin_c': Decimal('7.4'), 'sodium': Decimal('4'),
    },
    {
        'name': 'Potato', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('77'), 'protein': Decimal('2.0'), 'carbs': Decimal('17.5'),
        'fat': Decimal('0.1'), 'fiber': Decimal('2.2'), 'sugar': Decimal('0.8'),
        'iron': Decimal('0.8'), 'calcium': Decimal('12'), 'b12': Decimal('0'),
        'zinc': Decimal('0.3'), 'magnesium': Decimal('23'), 'vitamin_c': Decimal('19.7'), 'sodium': Decimal('6'),
    },
    {
        'name': 'Broccoli', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('34'), 'protein': Decimal('2.8'), 'carbs': Decimal('7.0'),
        'fat': Decimal('0.4'), 'fiber': Decimal('2.6'), 'sugar': Decimal('1.7'),
        'iron': Decimal('0.7'), 'calcium': Decimal('47'), 'b12': Decimal('0'),
        'zinc': Decimal('0.4'), 'magnesium': Decimal('21'), 'vitamin_c': Decimal('89'), 'sodium': Decimal('33'),
    },
    {
        'name': 'Bell Pepper (Capsicum)', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('31'), 'protein': Decimal('1.0'), 'carbs': Decimal('6.0'),
        'fat': Decimal('0.3'), 'fiber': Decimal('2.1'), 'sugar': Decimal('4.2'),
        'iron': Decimal('0.4'), 'calcium': Decimal('7'), 'b12': Decimal('0'),
        'zinc': Decimal('0.3'), 'magnesium': Decimal('12'), 'vitamin_c': Decimal('127'), 'sodium': Decimal('4'),
    },
    {
        'name': 'Green Peas', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('81'), 'protein': Decimal('5.4'), 'carbs': Decimal('14.5'),
        'fat': Decimal('0.4'), 'fiber': Decimal('5.1'), 'sugar': Decimal('5.7'),
        'iron': Decimal('1.5'), 'calcium': Decimal('25'), 'b12': Decimal('0'),
        'zinc': Decimal('1.2'), 'magnesium': Decimal('33'), 'vitamin_c': Decimal('40'), 'sodium': Decimal('5'),
    },
    {
        'name': 'Cauliflower', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('25'), 'protein': Decimal('1.9'), 'carbs': Decimal('5.0'),
        'fat': Decimal('0.3'), 'fiber': Decimal('2.5'), 'sugar': Decimal('1.9'),
        'iron': Decimal('0.4'), 'calcium': Decimal('22'), 'b12': Decimal('0'),
        'zinc': Decimal('0.3'), 'magnesium': Decimal('15'), 'vitamin_c': Decimal('48'), 'sodium': Decimal('30'),
    },
    {
        'name': 'Sweet Potato', 'category': 'vegetable', 'is_vegan': True,
        'calories': Decimal('86'), 'protein': Decimal('1.6'), 'carbs': Decimal('20.1'),
        'fat': Decimal('0.1'), 'fiber': Decimal('3.0'), 'sugar': Decimal('4.2'),
        'iron': Decimal('0.6'), 'calcium': Decimal('30'), 'b12': Decimal('0'),
        'zinc': Decimal('0.3'), 'magnesium': Decimal('25'), 'vitamin_c': Decimal('2.4'), 'sodium': Decimal('55'),
    },
    # --- Nuts & Seeds ---
    {
        'name': 'Almonds', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('579'), 'protein': Decimal('21.2'), 'carbs': Decimal('21.6'),
        'fat': Decimal('49.9'), 'fiber': Decimal('12.5'), 'sugar': Decimal('4.4'),
        'iron': Decimal('3.7'), 'calcium': Decimal('264'), 'b12': Decimal('0'),
        'zinc': Decimal('3.1'), 'magnesium': Decimal('270'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('1'),
    },
    {
        'name': 'Cashew Nuts', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('553'), 'protein': Decimal('18.2'), 'carbs': Decimal('30.2'),
        'fat': Decimal('43.8'), 'fiber': Decimal('3.3'), 'sugar': Decimal('5.9'),
        'iron': Decimal('6.7'), 'calcium': Decimal('37'), 'b12': Decimal('0'),
        'zinc': Decimal('5.8'), 'magnesium': Decimal('292'), 'vitamin_c': Decimal('0.5'), 'sodium': Decimal('12'),
    },
    {
        'name': 'Chia Seeds', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('486'), 'protein': Decimal('16.5'), 'carbs': Decimal('42.1'),
        'fat': Decimal('30.7'), 'fiber': Decimal('34.4'), 'sugar': Decimal('0'),
        'iron': Decimal('7.7'), 'calcium': Decimal('631'), 'b12': Decimal('0'),
        'zinc': Decimal('4.6'), 'magnesium': Decimal('335'), 'vitamin_c': Decimal('1.6'), 'sodium': Decimal('16'),
    },
    {
        'name': 'Flax Seeds (Linseed)', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('534'), 'protein': Decimal('18.3'), 'carbs': Decimal('28.9'),
        'fat': Decimal('42.2'), 'fiber': Decimal('27.3'), 'sugar': Decimal('1.6'),
        'iron': Decimal('5.7'), 'calcium': Decimal('255'), 'b12': Decimal('0'),
        'zinc': Decimal('4.3'), 'magnesium': Decimal('392'), 'vitamin_c': Decimal('0.6'), 'sodium': Decimal('30'),
    },
    {
        'name': 'Pumpkin Seeds', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('559'), 'protein': Decimal('30.2'), 'carbs': Decimal('10.7'),
        'fat': Decimal('49.1'), 'fiber': Decimal('6.0'), 'sugar': Decimal('1.4'),
        'iron': Decimal('8.8'), 'calcium': Decimal('46'), 'b12': Decimal('0'),
        'zinc': Decimal('7.8'), 'magnesium': Decimal('592'), 'vitamin_c': Decimal('1.9'), 'sodium': Decimal('7'),
    },
    {
        'name': 'Sesame Seeds (Til)', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('573'), 'protein': Decimal('17.7'), 'carbs': Decimal('23.5'),
        'fat': Decimal('49.7'), 'fiber': Decimal('11.8'), 'sugar': Decimal('0.3'),
        'iron': Decimal('14.6'), 'calcium': Decimal('975'), 'b12': Decimal('0'),
        'zinc': Decimal('7.8'), 'magnesium': Decimal('351'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('11'),
    },
    {
        'name': 'Sunflower Seeds', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('584'), 'protein': Decimal('20.8'), 'carbs': Decimal('20.0'),
        'fat': Decimal('51.5'), 'fiber': Decimal('8.6'), 'sugar': Decimal('2.6'),
        'iron': Decimal('5.3'), 'calcium': Decimal('78'), 'b12': Decimal('0'),
        'zinc': Decimal('5.0'), 'magnesium': Decimal('325'), 'vitamin_c': Decimal('1.4'), 'sodium': Decimal('9'),
    },
    # --- Fruits ---
    {
        'name': 'Banana', 'category': 'fruit', 'is_vegan': True,
        'calories': Decimal('89'), 'protein': Decimal('1.1'), 'carbs': Decimal('22.8'),
        'fat': Decimal('0.3'), 'fiber': Decimal('2.6'), 'sugar': Decimal('12.2'),
        'iron': Decimal('0.3'), 'calcium': Decimal('5'), 'b12': Decimal('0'),
        'zinc': Decimal('0.2'), 'magnesium': Decimal('27'), 'vitamin_c': Decimal('8.7'), 'sodium': Decimal('1'),
    },
    {
        'name': 'Apple', 'category': 'fruit', 'is_vegan': True,
        'calories': Decimal('52'), 'protein': Decimal('0.3'), 'carbs': Decimal('13.8'),
        'fat': Decimal('0.2'), 'fiber': Decimal('2.4'), 'sugar': Decimal('10.4'),
        'iron': Decimal('0.1'), 'calcium': Decimal('6'), 'b12': Decimal('0'),
        'zinc': Decimal('0.0'), 'magnesium': Decimal('5'), 'vitamin_c': Decimal('4.6'), 'sodium': Decimal('1'),
    },
    {
        'name': 'Avocado', 'category': 'fruit', 'is_vegan': True,
        'calories': Decimal('160'), 'protein': Decimal('2.0'), 'carbs': Decimal('8.5'),
        'fat': Decimal('14.7'), 'fiber': Decimal('6.7'), 'sugar': Decimal('0.7'),
        'iron': Decimal('0.6'), 'calcium': Decimal('12'), 'b12': Decimal('0'),
        'zinc': Decimal('0.6'), 'magnesium': Decimal('29'), 'vitamin_c': Decimal('10'), 'sodium': Decimal('7'),
    },
    # --- Oils & Staples ---
    {
        'name': 'Olive Oil', 'category': 'oil', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('884'), 'protein': Decimal('0'), 'carbs': Decimal('0'),
        'fat': Decimal('100'), 'fiber': Decimal('0'), 'sugar': Decimal('0'),
        'iron': Decimal('0.6'), 'calcium': Decimal('1'), 'b12': Decimal('0'),
        'zinc': Decimal('0'), 'magnesium': Decimal('0'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('2'),
    },
    {
        'name': 'Coconut Oil', 'category': 'oil', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('892'), 'protein': Decimal('0'), 'carbs': Decimal('0'),
        'fat': Decimal('99.1'), 'fiber': Decimal('0'), 'sugar': Decimal('0'),
        'iron': Decimal('0'), 'calcium': Decimal('1'), 'b12': Decimal('0'),
        'zinc': Decimal('0'), 'magnesium': Decimal('0'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('0'),
    },
    {
        'name': 'Salt', 'category': 'spice', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('0'), 'protein': Decimal('0'), 'carbs': Decimal('0'),
        'fat': Decimal('0'), 'fiber': Decimal('0'), 'sugar': Decimal('0'),
        'iron': Decimal('0.3'), 'calcium': Decimal('24'), 'b12': Decimal('0'),
        'zinc': Decimal('0.1'), 'magnesium': Decimal('1'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('38758'),
    },
    {
        'name': 'Turmeric Powder', 'category': 'spice', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('354'), 'protein': Decimal('7.8'), 'carbs': Decimal('64.9'),
        'fat': Decimal('9.9'), 'fiber': Decimal('21.1'), 'sugar': Decimal('3.2'),
        'iron': Decimal('41.4'), 'calcium': Decimal('183'), 'b12': Decimal('0'),
        'zinc': Decimal('4.4'), 'magnesium': Decimal('193'), 'vitamin_c': Decimal('25.9'), 'sodium': Decimal('38'),
    },
    {
        'name': 'Cumin Seeds (Jeera)', 'category': 'spice', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('375'), 'protein': Decimal('17.8'), 'carbs': Decimal('44.2'),
        'fat': Decimal('22.3'), 'fiber': Decimal('10.5'), 'sugar': Decimal('2.3'),
        'iron': Decimal('66.4'), 'calcium': Decimal('931'), 'b12': Decimal('0'),
        'zinc': Decimal('4.8'), 'magnesium': Decimal('366'), 'vitamin_c': Decimal('7.7'), 'sodium': Decimal('168'),
    },
    {
        'name': 'Ginger (Fresh)', 'category': 'spice', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('80'), 'protein': Decimal('1.8'), 'carbs': Decimal('17.8'),
        'fat': Decimal('0.8'), 'fiber': Decimal('2.0'), 'sugar': Decimal('1.7'),
        'iron': Decimal('0.6'), 'calcium': Decimal('16'), 'b12': Decimal('0'),
        'zinc': Decimal('0.3'), 'magnesium': Decimal('43'), 'vitamin_c': Decimal('5.0'), 'sodium': Decimal('13'),
    },
    {
        'name': 'Garlic', 'category': 'spice', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('149'), 'protein': Decimal('6.4'), 'carbs': Decimal('33.1'),
        'fat': Decimal('0.5'), 'fiber': Decimal('2.1'), 'sugar': Decimal('1.0'),
        'iron': Decimal('1.7'), 'calcium': Decimal('181'), 'b12': Decimal('0'),
        'zinc': Decimal('1.2'), 'magnesium': Decimal('25'), 'vitamin_c': Decimal('31'), 'sodium': Decimal('17'),
    },
    # --- Eggs ---
    {
        'name': 'Egg (Whole)', 'category': 'other', 'is_vegan': False,
        'calories': Decimal('155'), 'protein': Decimal('12.6'), 'carbs': Decimal('1.1'),
        'fat': Decimal('10.6'), 'fiber': Decimal('0'), 'sugar': Decimal('1.1'),
        'iron': Decimal('1.8'), 'calcium': Decimal('50'), 'b12': Decimal('0.89'),
        'zinc': Decimal('1.3'), 'magnesium': Decimal('12'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('124'),
    },
    # --- Other protein ---
    {
        'name': 'Peanuts', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('567'), 'protein': Decimal('25.8'), 'carbs': Decimal('16.1'),
        'fat': Decimal('49.2'), 'fiber': Decimal('8.5'), 'sugar': Decimal('4.7'),
        'iron': Decimal('4.6'), 'calcium': Decimal('92'), 'b12': Decimal('0'),
        'zinc': Decimal('3.3'), 'magnesium': Decimal('168'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('18'),
    },
    {
        'name': 'Peanut Butter', 'category': 'nut_seed', 'is_vegan': True,
        'calories': Decimal('589'), 'protein': Decimal('25.1'), 'carbs': Decimal('20.1'),
        'fat': Decimal('49.9'), 'fiber': Decimal('6.0'), 'sugar': Decimal('9.2'),
        'iron': Decimal('1.9'), 'calcium': Decimal('49'), 'b12': Decimal('0'),
        'zinc': Decimal('2.8'), 'magnesium': Decimal('154'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('429'),
    },
    {
        'name': 'Coconut Milk', 'category': 'other', 'is_vegan': True,
        'calories': Decimal('197'), 'protein': Decimal('2.0'), 'carbs': Decimal('2.8'),
        'fat': Decimal('21.3'), 'fiber': Decimal('2.2'), 'sugar': Decimal('3.3'),
        'iron': Decimal('1.6'), 'calcium': Decimal('16'), 'b12': Decimal('0'),
        'zinc': Decimal('0.7'), 'magnesium': Decimal('37'), 'vitamin_c': Decimal('2.8'), 'sodium': Decimal('15'),
    },
    {
        'name': 'Nutritional Yeast', 'category': 'other', 'is_vegan': True,
        'calories': Decimal('325'), 'protein': Decimal('50.0'), 'carbs': Decimal('31.0'),
        'fat': Decimal('7.7'), 'fiber': Decimal('25.0'), 'sugar': Decimal('1.0'),
        'iron': Decimal('5.0'), 'calcium': Decimal('110'), 'b12': Decimal('30.0'),
        'zinc': Decimal('7.0'), 'magnesium': Decimal('110'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('100'),
    },
    {
        'name': 'Soy Milk', 'category': 'other', 'is_vegan': True,
        'calories': Decimal('33'), 'protein': Decimal('3.3'), 'carbs': Decimal('1.5'),
        'fat': Decimal('1.9'), 'fiber': Decimal('0.5'), 'sugar': Decimal('1.0'),
        'iron': Decimal('0.6'), 'calcium': Decimal('25'), 'b12': Decimal('0.6'),
        'zinc': Decimal('0.3'), 'magnesium': Decimal('25'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('51'),
    },
    {
        'name': 'Lemon Juice', 'category': 'fruit', 'is_vegan': True,
        'calories': Decimal('22'), 'protein': Decimal('0.4'), 'carbs': Decimal('6.9'),
        'fat': Decimal('0.2'), 'fiber': Decimal('0.3'), 'sugar': Decimal('2.5'),
        'iron': Decimal('0.1'), 'calcium': Decimal('7'), 'b12': Decimal('0'),
        'zinc': Decimal('0.1'), 'magnesium': Decimal('6'), 'vitamin_c': Decimal('38.7'), 'sodium': Decimal('1'),
    },
    {
        'name': 'Poha (Flattened Rice)', 'category': 'grain', 'is_vegan': True,
        'calories': Decimal('357'), 'protein': Decimal('6.5'), 'carbs': Decimal('76.9'),
        'fat': Decimal('1.2'), 'fiber': Decimal('2.0'), 'sugar': Decimal('0'),
        'iron': Decimal('10.0'), 'calcium': Decimal('7'), 'b12': Decimal('0'),
        'zinc': Decimal('0.6'), 'magnesium': Decimal('30'), 'vitamin_c': Decimal('0'), 'sodium': Decimal('5'),
    },
    {
        'name': 'Mustard Seeds (Rai)', 'category': 'spice', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('508'), 'protein': Decimal('26.1'), 'carbs': Decimal('28.1'),
        'fat': Decimal('36.2'), 'fiber': Decimal('12.2'), 'sugar': Decimal('6.8'),
        'iron': Decimal('9.9'), 'calcium': Decimal('521'), 'b12': Decimal('0'),
        'zinc': Decimal('6.1'), 'magnesium': Decimal('370'), 'vitamin_c': Decimal('7.1'), 'sodium': Decimal('13'),
    },
    {
        'name': 'Curry Leaves', 'category': 'spice', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('108'), 'protein': Decimal('6.1'), 'carbs': Decimal('18.7'),
        'fat': Decimal('1.0'), 'fiber': Decimal('6.4'), 'sugar': Decimal('3.0'),
        'iron': Decimal('0.9'), 'calcium': Decimal('830'), 'b12': Decimal('0'),
        'zinc': Decimal('0.2'), 'magnesium': Decimal('44'), 'vitamin_c': Decimal('4.0'), 'sodium': Decimal('11'),
    },
    {
        'name': 'Coriander Leaves (Cilantro)', 'category': 'spice', 'is_vegan': True, 'is_staple': True,
        'calories': Decimal('23'), 'protein': Decimal('2.1'), 'carbs': Decimal('3.7'),
        'fat': Decimal('0.5'), 'fiber': Decimal('2.8'), 'sugar': Decimal('0.9'),
        'iron': Decimal('1.8'), 'calcium': Decimal('67'), 'b12': Decimal('0'),
        'zinc': Decimal('0.5'), 'magnesium': Decimal('26'), 'vitamin_c': Decimal('27'), 'sodium': Decimal('46'),
    },
    {
        'name': 'Tamarind', 'category': 'fruit', 'is_vegan': True,
        'calories': Decimal('239'), 'protein': Decimal('2.8'), 'carbs': Decimal('62.5'),
        'fat': Decimal('0.6'), 'fiber': Decimal('5.1'), 'sugar': Decimal('57.4'),
        'iron': Decimal('2.8'), 'calcium': Decimal('74'), 'b12': Decimal('0'),
        'zinc': Decimal('0.1'), 'magnesium': Decimal('92'), 'vitamin_c': Decimal('3.5'), 'sodium': Decimal('28'),
    },
]


# ---------------------------------------------------------------------------
# Recipe data
# ---------------------------------------------------------------------------

RECIPES = [
    {
        'title': 'Oats with soy milk',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 5,
        'cook_time': 5,
        'servings': 1,
        'description': 'Warm creamy rolled oats cooked in fortified soy milk and chia seeds, providing clean protein, iron and fiber.',
        'instructions': (
            '1. In a small pot, bring fortified soy milk to a gentle simmer over medium-low heat.\n'
            '2. Add rolled oats and chia seeds, stirring constantly for 3 to 4 minutes until thick and creamy.\n'
            '3. Pour into a bowl and enjoy warm.'
        ),
        'ingredients': [
            ('Rolled Oats', 60),
            ('Soy Milk', 200),
            ('Chia Seeds', 10),
        ],
    },
    {
        'title': 'Dal tadka',
        'diet_type': 'vegetarian',
        'meal_type': 'lunch',
        'prep_time': 10,
        'cook_time': 20,
        'servings': 2,
        'description': 'Golden simmered toor dal tempered with sizzling cumin, garlic, and aromatic spices in ghee.',
        'instructions': (
            '1. Rinse toor dal and cook with water, turmeric, and salt until tender and smooth.\n'
            '2. In a small tadka pan, heat ghee and add cumin seeds until they splutter.\n'
            '3. Sauté minced garlic, ginger, diced onions, and chopped tomatoes until fragrant.\n'
            '4. Pour the sizzling aromatic tadka over the dal and simmer for 2 minutes before serving.'
        ),
        'ingredients': [
            ('Toor Dal (Pigeon Peas)', 120),
            ('Tomato', 60),
            ('Onion', 50),
            ('Garlic', 10),
            ('Ghee (Clarified Butter)', 15),
        ],
    },
    {
        'title': 'Steamed rice',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 5,
        'cook_time': 15,
        'servings': 2,
        'description': 'Fluffy fragrant steamed basmati rice, the perfect pairing for hearty lentil dals.',
        'instructions': (
            '1. Rinse basmati rice thoroughly until the water runs clear.\n'
            '2. Bring 2 cups of water to a boil, add rinsed rice and a pinch of salt.\n'
            '3. Cover tightly, reduce heat to low, and cook undisturbed for 15 minutes.\n'
            '4. Remove from heat and gently fluff with a fork.'
        ),
        'ingredients': [
            ('Basmati Rice', 150),
        ],
    },
    {
        'title': 'Roasted chana',
        'diet_type': 'vegan',
        'meal_type': 'snack',
        'prep_time': 5,
        'cook_time': 15,
        'servings': 2,
        'description': 'Crispy oven-roasted chickpeas tossed in cold-pressed olive oil and savoury spices.',
        'instructions': (
            '1. Drain and pat chickpeas completely dry with a kitchen towel.\n'
            '2. Toss with olive oil, turmeric, and sea salt.\n'
            '3. Roast in an oven or skillet on medium-high heat until golden brown and super crunchy.'
        ),
        'ingredients': [
            ('Chickpeas (Chana)', 160),
            ('Olive Oil', 10),
        ],
    },
    {
        'title': 'Palak Tofu',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 15,
        'servings': 2,
        'description': 'Tender seared tofu cubes folded into a spiced velvety spinach gravy — iron-rich and protein packed.',
        'instructions': (
            '1. Blanch spinach in salted boiling water for 2 minutes, then transfer to ice water and blend into a smooth purée.\n'
            '2. Heat olive oil in a pan; lightly sear cubed tofu on all sides until golden. Remove and set aside.\n'
            '3. In the same pan, add cumin seeds, chopped garlic, ginger, and diced onions. Sauté until fragrant and translucent.\n'
            '4. Add finely chopped tomatoes and turmeric powder; simmer until tomatoes break down.\n'
            '5. Pour in the vibrant spinach purée, stir in the golden tofu cubes, and season with salt.\n'
            '6. Simmer on low heat for 5 minutes and serve warm with brown rice or roti.'
        ),
        'ingredients': [
            ('Spinach (Palak)', 200),
            ('Tofu (Firm)', 250),
            ('Onion', 80),
            ('Tomato', 80),
            ('Garlic', 10),
            ('Ginger (Fresh)', 5),
            ('Olive Oil', 10),
            ('Cumin Seeds (Jeera)', 3),
            ('Turmeric Powder', 2),
            ('Salt', 3),
        ],
    },
    {
        'title': 'Tomato Dal',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 20,
        'servings': 2,
        'description': 'Hearty red lentils gently simmered with juicy ripe tomatoes and a golden cumin-ghee tadka.',
        'instructions': (
            '1. Rinse red lentils thoroughly and simmer with turmeric and water until soft and creamy.\n'
            '2. Heat ghee (or oil for vegan); add cumin seeds, sliced garlic, and chopped onion until golden.\n'
            '3. Add chopped fresh tomatoes and cook down until tender and aromatic.\n'
            '4. Pour the sizzling tomato tadka into the cooked dal and stir well.\n'
            '5. Simmer for 5 minutes and serve hot with fluffy basmati rice.'
        ),
        'ingredients': [
            ('Red Lentils (Masoor Dal)', 150),
            ('Tomato', 150),
            ('Onion', 80),
            ('Garlic', 10),
            ('Ghee (Clarified Butter)', 10),
            ('Cumin Seeds (Jeera)', 4),
            ('Turmeric Powder', 3),
            ('Salt', 4),
        ],
    },
    {
        'title': 'Quinoa Bowl',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 10,
        'cook_time': 15,
        'servings': 2,
        'description': 'Wholesome fluffy quinoa loaded with spiced chickpeas, fresh greens, and crunchy toasted pumpkin seeds.',
        'instructions': (
            '1. Rinse and simmer quinoa in water for 15 minutes until tender and fluffy.\n'
            '2. Toss warm chickpeas with olive oil, cumin, salt, and fresh lemon juice.\n'
            '3. Arrange a bed of fresh baby spinach and chopped tomatoes in serving bowls.\n'
            '4. Layer warm quinoa and seasoned chickpeas on top.\n'
            '5. Garnish with toasted pumpkin seeds and a squeeze of fresh lemon.'
        ),
        'ingredients': [
            ('Quinoa', 120),
            ('Chickpeas (Chana)', 150),
            ('Spinach (Palak)', 80),
            ('Tomato', 80),
            ('Olive Oil', 10),
            ('Pumpkin Seeds', 20),
            ('Salt', 3),
            ('Lemon Juice', 10),
        ],
    },
    {
        'title': 'Chana Bowl',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 10,
        'cook_time': 10,
        'servings': 2,
        'description': 'High-protein seasoned chickpeas over nutty brown rice with lemon, onions, and fresh cilantro.',
        'instructions': (
            '1. Warm cooked brown rice in serving bowls.\n'
            '2. Sauté cooked chickpeas in olive oil with cumin seeds, onions, and salt until fragrant.\n'
            '3. Spoon seasoned chickpeas generously over the rice.\n'
            '4. Top with diced tomatoes and drizzle fresh lemon juice over the bowl.'
        ),
        'ingredients': [
            ('Chickpeas (Chana)', 250),
            ('Brown Rice', 150),
            ('Onion', 60),
            ('Tomato', 80),
            ('Olive Oil', 10),
            ('Cumin Seeds (Jeera)', 3),
            ('Lemon Juice', 10),
            ('Salt', 3),
        ],
    },
    {
        'title': 'Rajma Masala',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 25,
        'servings': 4,
        'description': 'Classic Punjabi kidney bean curry stewed in a rich tomato, ginger, and cumin gravy.',
        'instructions': (
            '1. Heat olive oil in a pan; add cumin seeds, minced garlic, and ginger paste.\n'
            '2. Add finely diced onions and cook until rich golden brown.\n'
            '3. Stir in pureed tomatoes and spices, cooking until fragrant.\n'
            '4. Add tender kidney beans along with cooking liquid; lightly mash a few beans to thicken the gravy.\n'
            '5. Simmer gently for 20 minutes until velvety and deep in flavour.'
        ),
        'ingredients': [
            ('Kidney Beans (Rajma)', 300),
            ('Tomato', 200),
            ('Onion', 150),
            ('Garlic', 15),
            ('Ginger (Fresh)', 10),
            ('Olive Oil', 15),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Salt', 5),
        ],
    },
    {
        'title': 'Overnight Oats',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 5,
        'cook_time': 0,
        'servings': 1,
        'description': 'Creamy overnight rolled oats soaked in fortified soy milk with chia seeds, banana slices, and toasted almonds.',
        'instructions': (
            '1. In a jar or bowl, combine rolled oats, chia seeds, and fortified soy milk.\n'
            '2. Stir well and refrigerate overnight (or at least 4 hours) to thicken.\n'
            '3. In the morning, top with freshly sliced banana and crunchy chopped almonds.\n'
            '4. Enjoy chilled for an energizing high-fibre plant breakfast.'
        ),
        'ingredients': [
            ('Rolled Oats', 60),
            ('Soy Milk', 200),
            ('Chia Seeds', 15),
            ('Banana', 80),
            ('Almonds', 15),
        ],
    },
    {
        'title': 'Palak Paneer',
        'diet_type': 'vegetarian',
        'meal_type': 'dinner',
        'prep_time': 15,
        'cook_time': 20,
        'servings': 3,
        'description': 'Soft cottage cheese cubes simmered in spiced vibrant spinach gravy — calcium and protein powerhouse.',
        'instructions': (
            '1. Blanch spinach and blend into a smooth puree.\n'
            '2. Heat ghee; sauté cumin seeds, garlic, ginger, and onions until translucent.\n'
            '3. Add tomatoes, turmeric, and salt; cook until soft.\n'
            '4. Stir in spinach puree and simmer for 5 minutes.\n'
            '5. Gently fold in fresh paneer cubes and warm through before serving.'
        ),
        'ingredients': [
            ('Paneer (Indian Cottage Cheese)', 250),
            ('Spinach (Palak)', 300),
            ('Onion', 100),
            ('Tomato', 100),
            ('Ghee (Clarified Butter)', 15),
            ('Garlic', 15),
            ('Ginger (Fresh)', 10),
            ('Cumin Seeds (Jeera)', 4),
            ('Turmeric Powder', 3),
            ('Salt', 5),
        ],
    },
    {
        'title': 'Chickpea Buddha Bowl',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 10,
        'cook_time': 20,
        'servings': 2,
        'description': 'Nutrient-packed bowl with roasted sweet potato, spiced chickpeas, fluffy quinoa, and toasted sesame seeds.',
        'instructions': (
            '1. Roast diced sweet potato with a drop of olive oil and salt until caramelized.\n'
            '2. Cook quinoa until light and fluffy.\n'
            '3. Assemble bowl with a base of spinach, cooked quinoa, chickpeas, and sweet potatoes.\n'
            '4. Drizzle fresh lemon juice and sprinkle toasted sesame seeds on top.'
        ),
        'ingredients': [
            ('Chickpeas (Chana)', 200),
            ('Quinoa', 100),
            ('Sweet Potato', 120),
            ('Spinach (Palak)', 60),
            ('Sesame Seeds (Til)', 15),
            ('Olive Oil', 10),
            ('Lemon Juice', 10),
            ('Salt', 3),
        ],
    },
    {
        'title': 'Moong Dal Cheela',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 10,
        'cook_time': 15,
        'servings': 2,
        'description': 'Savory golden lentil crepes stuffed with chopped onions and capsicum — quick, crispy, and high protein.',
        'instructions': (
            '1. Soak moong dal and blend with ginger and salt into a smooth pourable batter.\n'
            '2. Heat a non-stick tawa or skillet with a few drops of olive oil.\n'
            '3. Pour a ladle of batter and spread in a circular motion.\n'
            '4. Sprinkle finely chopped onions and cumin seeds on top, press gently.\n'
            '5. Flip and cook until golden brown on both sides. Serve with mint chutney.'
        ),
        'ingredients': [
            ('Moong Dal (Split Mung Beans)', 150),
            ('Onion', 60),
            ('Ginger (Fresh)', 5),
            ('Olive Oil', 10),
            ('Cumin Seeds (Jeera)', 3),
            ('Salt', 3),
        ],
    },
    {
        'title': 'Soybean Keema Matar',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 20,
        'servings': 3,
        'description': 'Spiced plant protein mince simmered with sweet green peas in a rich onion-tomato masala.',
        'instructions': (
            '1. Cook lentils/mince until tender and set aside.\n'
            '2. Heat olive oil; add cumin seeds, minced garlic, and onions until browned.\n'
            '3. Add tomatoes, turmeric, and spices; cook until oil glazes the edges.\n'
            '4. Add green peas and protein mince; simmer with 1/2 cup water for 12 minutes.\n'
            '5. Garnish with fresh cilantro and serve with warm roti.'
        ),
        'ingredients': [
            ('Green Peas', 150),
            ('Red Lentils (Masoor Dal)', 120),
            ('Onion', 100),
            ('Tomato', 150),
            ('Garlic', 10),
            ('Olive Oil', 15),
            ('Cumin Seeds (Jeera)', 4),
            ('Turmeric Powder', 3),
            ('Salt', 4),
        ],
    },
    {
        'title': 'Chia Berry Parfait',
        'diet_type': 'vegan',
        'meal_type': 'snack',
        'prep_time': 5,
        'cook_time': 0,
        'servings': 1,
        'description': 'Chilled chia seed pudding layered with sliced bananas, crunchy almonds, and fortified plant milk.',
        'instructions': (
            '1. Whisk chia seeds into fortified soy milk with a pinch of cinnamon.\n'
            '2. Chill in the fridge for 2 hours until gel-like and creamy.\n'
            '3. Layer into a glass with sliced ripe banana.\n'
            '4. Top with sliced toasted almonds for a high-omega crunch.'
        ),
        'ingredients': [
            ('Chia Seeds', 25),
            ('Soy Milk', 150),
            ('Banana', 80),
            ('Almonds', 15),
        ],
    },
    {
        'title': 'Moroccan Lentil Stew',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 30,
        'servings': 4,
        'description': 'Warm spiced stew with green lentils, sweet potatoes, tomatoes, and aromatic cumin and turmeric.',
        'instructions': (
            '1. Heat olive oil in a heavy pot; sauté onions, garlic, and cumin seeds.\n'
            '2. Add cubed sweet potatoes, rinsed green lentils, and pureed tomatoes.\n'
            '3. Pour in 3 cups water, add turmeric and salt, and bring to a simmer.\n'
            '4. Cover and cook on medium-low for 25 minutes until lentils and sweet potatoes are fork-tender.\n'
            '5. Serve in warm bowls with a squeeze of fresh lemon.'
        ),
        'ingredients': [
            ('Green Lentils', 200),
            ('Sweet Potato', 150),
            ('Tomato', 150),
            ('Onion', 100),
            ('Olive Oil', 15),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Salt', 5),
        ],
    },
    {
        'title': 'Dal Tadka',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 10,
        'cook_time': 30,
        'servings': 4,
        'description': 'Classic Indian tempered lentil soup — comforting, protein-rich, and full of flavour.',
        'instructions': (
            '1. Rinse lentils and cook with 3 cups water, turmeric, and salt for 20 minutes.\n'
            '2. Heat oil; add cumin seeds and let splutter.\n'
            '3. Add garlic and ginger; sauté 1 minute.\n'
            '4. Add onion; cook until golden.\n'
            '5. Add tomatoes; cook until soft.\n'
            '6. Pour tempering over dal, stir and simmer 5 minutes.\n'
            '7. Garnish with coriander and serve with rice or roti.'
        ),
        'ingredients': [
            ('Toor Dal (Pigeon Peas)', 200),
            ('Onion', 100),
            ('Tomato', 100),
            ('Ghee (Clarified Butter)', 15),
            ('Garlic', 10),
            ('Ginger (Fresh)', 10),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Salt', 5),
            ('Coriander Leaves (Cilantro)', 10),
        ],
    },
    {
        'title': 'Chana Masala',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 15,
        'cook_time': 40,
        'servings': 4,
        'description': 'Spiced chickpea curry — high protein, high fibre, and deeply satisfying.',
        'instructions': (
            '1. Heat oil; add onion and cook until golden.\n'
            '2. Add garlic and ginger paste; cook 2 minutes.\n'
            '3. Add tomatoes and spices; cook until oil separates.\n'
            '4. Add drained chickpeas and 1 cup water.\n'
            '5. Simmer 20 minutes until thick.\n'
            '6. Garnish with coriander and lemon juice.'
        ),
        'ingredients': [
            ('Chickpeas (Chana)', 300),
            ('Onion', 150),
            ('Tomato', 200),
            ('Olive Oil', 15),
            ('Garlic', 15),
            ('Ginger (Fresh)', 10),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Salt', 5),
            ('Coriander Leaves (Cilantro)', 15),
            ('Lemon Juice', 15),
        ],
    },
    {
        'title': 'Paneer Bhurji',
        'diet_type': 'vegetarian',
        'meal_type': 'breakfast',
        'prep_time': 10,
        'cook_time': 15,
        'servings': 2,
        'description': 'Scrambled paneer with spices and vegetables — a protein-packed Indian breakfast.',
        'instructions': (
            '1. Heat ghee in a pan; add cumin seeds.\n'
            '2. Add onion and cook until softened.\n'
            '3. Add garlic, ginger and capsicum; cook 2 minutes.\n'
            '4. Add tomatoes and spices; cook 3 minutes.\n'
            '5. Crumble paneer into the pan; mix well.\n'
            '6. Season and garnish with coriander.'
        ),
        'ingredients': [
            ('Paneer (Indian Cottage Cheese)', 200),
            ('Onion', 80),
            ('Tomato', 80),
            ('Bell Pepper (Capsicum)', 60),
            ('Ghee (Clarified Butter)', 10),
            ('Garlic', 10),
            ('Ginger (Fresh)', 5),
            ('Cumin Seeds (Jeera)', 3),
            ('Turmeric Powder', 2),
            ('Salt', 3),
            ('Coriander Leaves (Cilantro)', 10),
        ],
    },
    {
        'title': 'Rajma Chawal',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 15,
        'cook_time': 45,
        'servings': 4,
        'description': 'Kidney bean curry served with rice — a North Indian comfort classic.',
        'instructions': (
            '1. Pressure cook rajma with water until tender.\n'
            '2. Prepare onion-tomato masala with garlic and ginger.\n'
            '3. Add spices; cook until fragrant.\n'
            '4. Add rajma and simmer 15 minutes.\n'
            '5. Serve over cooked basmati rice.'
        ),
        'ingredients': [
            ('Kidney Beans (Rajma)', 250),
            ('Basmati Rice', 200),
            ('Onion', 150),
            ('Tomato', 200),
            ('Olive Oil', 15),
            ('Garlic', 15),
            ('Ginger (Fresh)', 10),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Salt', 5),
        ],
    },
    {
        'title': 'Poha (Flattened Rice Breakfast)',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 10,
        'cook_time': 10,
        'servings': 2,
        'description': 'Light, quick Indian breakfast of flattened rice with mustard seeds, curry leaves, and veggies.',
        'instructions': (
            '1. Rinse poha under water; drain and set aside.\n'
            '2. Heat oil; add mustard seeds and curry leaves.\n'
            '3. Add onion and green chilli; cook 2 minutes.\n'
            '4. Add potato; cook 5 minutes.\n'
            '5. Add poha, salt, and turmeric; mix gently.\n'
            '6. Cover and cook 2 minutes.\n'
            '7. Garnish with coriander and lemon juice.'
        ),
        'ingredients': [
            ('Poha (Flattened Rice)', 150),
            ('Onion', 80),
            ('Potato', 100),
            ('Olive Oil', 10),
            ('Mustard Seeds (Rai)', 5),
            ('Curry Leaves', 5),
            ('Turmeric Powder', 2),
            ('Salt', 3),
            ('Coriander Leaves (Cilantro)', 10),
            ('Lemon Juice', 10),
        ],
    },
    {
        'title': 'Tofu Scramble',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 5,
        'cook_time': 10,
        'servings': 2,
        'description': 'High-protein vegan scramble with tofu, spinach, and nutritional yeast.',
        'instructions': (
            '1. Drain and crumble tofu.\n'
            '2. Heat oil; add garlic and cook 30 seconds.\n'
            '3. Add crumbled tofu; cook 3 minutes.\n'
            '4. Add spinach; cook until wilted.\n'
            '5. Season with turmeric, salt, and nutritional yeast.\n'
            '6. Serve hot.'
        ),
        'ingredients': [
            ('Tofu (Firm)', 300),
            ('Spinach (Palak)', 100),
            ('Nutritional Yeast', 15),
            ('Olive Oil', 10),
            ('Garlic', 10),
            ('Turmeric Powder', 2),
            ('Salt', 3),
        ],
    },
    {
        'title': 'Quinoa Buddha Bowl',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 10,
        'cook_time': 20,
        'servings': 2,
        'description': 'Nourishing bowl of quinoa, roasted vegetables, chickpeas, and tahini dressing.',
        'instructions': (
            '1. Cook quinoa in 2× water for 15 minutes.\n'
            '2. Roast chickpeas and vegetables with olive oil.\n'
            '3. Arrange quinoa in bowls; top with roasted items.\n'
            '4. Add spinach and avocado.\n'
            '5. Drizzle with lemon juice and sesame seeds.'
        ),
        'ingredients': [
            ('Quinoa', 150),
            ('Chickpeas (Chana)', 150),
            ('Spinach (Palak)', 80),
            ('Avocado', 100),
            ('Broccoli', 100),
            ('Olive Oil', 15),
            ('Sesame Seeds (Til)', 10),
            ('Lemon Juice', 20),
            ('Salt', 3),
        ],
    },
    {
        'title': 'Overnight Oats with Chia',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 5,
        'cook_time': 0,
        'servings': 1,
        'description': 'Creamy no-cook breakfast jar with oats, chia seeds, banana, and almond milk.',
        'instructions': (
            '1. Combine oats, chia seeds, and soy milk in a jar.\n'
            '2. Stir well; refrigerate overnight.\n'
            '3. Top with sliced banana and a handful of almonds.\n'
            '4. Drizzle with peanut butter if desired.'
        ),
        'ingredients': [
            ('Rolled Oats', 60),
            ('Chia Seeds', 15),
            ('Soy Milk', 200),
            ('Banana', 80),
            ('Almonds', 20),
            ('Peanut Butter', 15),
        ],
    },
    {
        'title': 'Palak Dal',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 30,
        'servings': 4,
        'description': 'Iron-rich spinach and lentil dal — earthy, nutritious, and warming.',
        'instructions': (
            '1. Cook lentils with turmeric until soft.\n'
            '2. Heat oil; add cumin, garlic, onion, tomatoes.\n'
            '3. Add blanched spinach; purée or leave chunky.\n'
            '4. Mix into cooked dal; simmer 10 minutes.\n'
            '5. Season and serve with roti or rice.'
        ),
        'ingredients': [
            ('Red Lentils (Masoor Dal)', 200),
            ('Spinach (Palak)', 150),
            ('Onion', 100),
            ('Tomato', 100),
            ('Olive Oil', 15),
            ('Garlic', 10),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Salt', 5),
        ],
    },
    {
        'title': 'Tempeh Stir-Fry',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 15,
        'servings': 2,
        'description': 'High-protein tempeh stir-fried with broccoli, bell pepper, and ginger.',
        'instructions': (
            '1. Slice tempeh; pan-fry until golden.\n'
            '2. Remove tempeh; add vegetables to the pan.\n'
            '3. Add garlic, ginger, and sauce.\n'
            '4. Return tempeh; toss to coat.\n'
            '5. Serve over brown rice or quinoa.'
        ),
        'ingredients': [
            ('Tempeh', 200),
            ('Broccoli', 150),
            ('Bell Pepper (Capsicum)', 100),
            ('Garlic', 10),
            ('Ginger (Fresh)', 10),
            ('Olive Oil', 15),
            ('Sesame Seeds (Til)', 10),
            ('Salt', 3),
        ],
    },
    {
        'title': 'Moong Dal Cheela (Lentil Crepes)',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 20,
        'cook_time': 20,
        'servings': 4,
        'description': 'Protein-rich savoury pancakes made from split mung beans with herbs and spices.',
        'instructions': (
            '1. Soak moong dal 4 hours; drain.\n'
            '2. Blend into a smooth batter with ginger, salt, and water.\n'
            '3. Add coriander to batter.\n'
            '4. Pour ladle of batter onto hot oiled pan; spread thin.\n'
            '5. Cook until edges crisp; flip and cook 1 minute.\n'
            '6. Serve with curd or chutney.'
        ),
        'ingredients': [
            ('Moong Dal (Split Mung Beans)', 200),
            ('Ginger (Fresh)', 10),
            ('Coriander Leaves (Cilantro)', 15),
            ('Olive Oil', 10),
            ('Salt', 4),
        ],
    },
    {
        'title': 'Aloo Gobi (Potato & Cauliflower)',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 25,
        'servings': 4,
        'description': 'Classic North Indian dry-spiced potato and cauliflower stir-fry.',
        'instructions': (
            '1. Heat oil; add cumin seeds.\n'
            '2. Add potatoes; par-cook 5 minutes.\n'
            '3. Add cauliflower, spices, and salt.\n'
            '4. Cover and cook on low heat 15 minutes.\n'
            '5. Garnish with coriander.'
        ),
        'ingredients': [
            ('Potato', 300),
            ('Cauliflower', 300),
            ('Onion', 100),
            ('Tomato', 80),
            ('Olive Oil', 15),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Garlic', 10),
            ('Salt', 4),
            ('Coriander Leaves (Cilantro)', 10),
        ],
    },
    {
        'title': 'High-Protein Smoothie Bowl',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 5,
        'cook_time': 0,
        'servings': 1,
        'description': 'Creamy frozen banana base loaded with seeds, nuts, and peanut butter.',
        'instructions': (
            '1. Blend frozen banana with soy milk until smooth.\n'
            '2. Pour into bowl.\n'
            '3. Top with chia seeds, pumpkin seeds, almonds, and peanut butter.\n'
            '4. Serve immediately.'
        ),
        'ingredients': [
            ('Banana', 150),
            ('Soy Milk', 100),
            ('Chia Seeds', 15),
            ('Pumpkin Seeds', 20),
            ('Almonds', 20),
            ('Peanut Butter', 20),
        ],
    },
    {
        'title': 'Quinoa & Lentil Soup',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 10,
        'cook_time': 30,
        'servings': 4,
        'description': 'Hearty, iron-rich soup with quinoa, red lentils, and vegetables.',
        'instructions': (
            '1. Sauté onion, garlic, and ginger in oil.\n'
            '2. Add tomatoes, spices, and cook 3 minutes.\n'
            '3. Add lentils, quinoa, and 4 cups water.\n'
            '4. Simmer 25 minutes until thick and creamy.\n'
            '5. Add spinach; cook 2 minutes.\n'
            '6. Season and serve.'
        ),
        'ingredients': [
            ('Red Lentils (Masoor Dal)', 150),
            ('Quinoa', 100),
            ('Spinach (Palak)', 100),
            ('Onion', 100),
            ('Tomato', 150),
            ('Garlic', 10),
            ('Ginger (Fresh)', 10),
            ('Olive Oil', 15),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Salt', 5),
        ],
    },
    {
        'title': 'Paneer Tikka Skewers',
        'diet_type': 'vegetarian',
        'meal_type': 'snack',
        'prep_time': 20,
        'cook_time': 20,
        'servings': 4,
        'description': 'Marinated paneer and vegetable skewers grilled to perfection.',
        'instructions': (
            '1. Cube paneer and vegetables.\n'
            '2. Mix yogurt with spices for marinade.\n'
            '3. Marinate paneer and veggies 30 minutes.\n'
            '4. Thread onto skewers; grill or bake at 220°C for 15 minutes.\n'
            '5. Serve with coriander chutney.'
        ),
        'ingredients': [
            ('Paneer (Indian Cottage Cheese)', 300),
            ('Bell Pepper (Capsicum)', 150),
            ('Onion', 100),
            ('Curd / Plain Yogurt', 100),
            ('Olive Oil', 15),
            ('Garlic', 10),
            ('Ginger (Fresh)', 10),
            ('Lemon Juice', 15),
            ('Salt', 4),
        ],
    },
    {
        'title': 'Avocado Toast with Sesame',
        'diet_type': 'vegan',
        'meal_type': 'breakfast',
        'prep_time': 5,
        'cook_time': 5,
        'servings': 1,
        'description': 'Creamy avocado on wholegrain toast with sesame seeds and lemon.',
        'instructions': (
            '1. Toast whole wheat bread.\n'
            '2. Mash avocado with lemon juice and salt.\n'
            '3. Spread on toast.\n'
            '4. Top with sesame seeds and chilli flakes.'
        ),
        'ingredients': [
            ('Avocado', 100),
            ('Whole Wheat Flour (Atta)', 60),
            ('Sesame Seeds (Til)', 10),
            ('Lemon Juice', 10),
            ('Salt', 2),
        ],
    },
    {
        'title': 'Rajma Stuffed Roti',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 20,
        'cook_time': 20,
        'servings': 2,
        'description': 'Protein-rich flatbread stuffed with spiced kidney beans.',
        'instructions': (
            '1. Mash cooked rajma with spices and herbs.\n'
            '2. Knead whole wheat dough; rest 15 minutes.\n'
            '3. Roll out dough; fill with rajma mixture.\n'
            '4. Seal and roll thin; cook on hot tawa with ghee.'
        ),
        'ingredients': [
            ('Kidney Beans (Rajma)', 150),
            ('Whole Wheat Flour (Atta)', 150),
            ('Ghee (Clarified Butter)', 10),
            ('Onion', 60),
            ('Cumin Seeds (Jeera)', 3),
            ('Coriander Leaves (Cilantro)', 10),
            ('Salt', 3),
        ],
    },
    {
        'title': 'Spinach & Tofu Curry',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 25,
        'servings': 4,
        'description': 'Iron and protein-packed vegan palak-style curry with firm tofu.',
        'instructions': (
            '1. Blanch spinach; purée with cashews.\n'
            '2. Pan-fry tofu cubes until golden; set aside.\n'
            '3. Sauté onion, garlic, ginger, and spices.\n'
            '4. Add spinach purée; simmer 5 minutes.\n'
            '5. Add tofu; cook 5 more minutes.\n'
            '6. Serve with roti.'
        ),
        'ingredients': [
            ('Tofu (Firm)', 300),
            ('Spinach (Palak)', 300),
            ('Cashew Nuts', 30),
            ('Onion', 100),
            ('Garlic', 15),
            ('Ginger (Fresh)', 10),
            ('Olive Oil', 15),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Salt', 5),
        ],
    },
    {
        'title': 'Chia Pudding',
        'diet_type': 'vegan',
        'meal_type': 'snack',
        'prep_time': 5,
        'cook_time': 0,
        'servings': 2,
        'description': 'Creamy calcium-rich chia pudding with banana and flax seeds.',
        'instructions': (
            '1. Combine chia seeds with soy milk and stir well.\n'
            '2. Refrigerate at least 4 hours.\n'
            '3. Top with sliced banana and flax seeds.\n'
            '4. Sweeten with a little jaggery if desired.'
        ),
        'ingredients': [
            ('Chia Seeds', 40),
            ('Soy Milk', 250),
            ('Banana', 100),
            ('Flax Seeds (Linseed)', 10),
        ],
    },
    {
        'title': 'Black Bean & Sweet Potato Bowl',
        'diet_type': 'vegan',
        'meal_type': 'lunch',
        'prep_time': 10,
        'cook_time': 25,
        'servings': 2,
        'description': 'Vibrant bowl of roasted sweet potato, black-eyed peas, and quinoa.',
        'instructions': (
            '1. Roast sweet potato with olive oil and salt at 200°C for 20 minutes.\n'
            '2. Cook quinoa; fluff with fork.\n'
            '3. Warm black-eyed peas with cumin and garlic.\n'
            '4. Assemble bowls; top with avocado and lemon juice.'
        ),
        'ingredients': [
            ('Sweet Potato', 200),
            ('Black-Eyed Peas (Lobia)', 150),
            ('Quinoa', 100),
            ('Avocado', 80),
            ('Olive Oil', 15),
            ('Garlic', 10),
            ('Cumin Seeds (Jeera)', 3),
            ('Lemon Juice', 15),
            ('Salt', 4),
        ],
    },
    {
        'title': 'Methi Paratha (Fenugreek Flatbread)',
        'diet_type': 'vegetarian',
        'meal_type': 'breakfast',
        'prep_time': 20,
        'cook_time': 20,
        'servings': 4,
        'description': 'Whole wheat flatbread enriched with fresh fenugreek, iron, and fibre.',
        'instructions': (
            '1. Combine flour, salt, and roughly chopped greens.\n'
            '2. Add curd and knead into soft dough with water.\n'
            '3. Rest 15 minutes; divide into balls.\n'
            '4. Roll each ball thin; cook on hot tawa with ghee.\n'
            '5. Serve with curd or pickle.'
        ),
        'ingredients': [
            ('Whole Wheat Flour (Atta)', 200),
            ('Spinach (Palak)', 80),
            ('Curd / Plain Yogurt', 50),
            ('Ghee (Clarified Butter)', 15),
            ('Cumin Seeds (Jeera)', 3),
            ('Salt', 4),
        ],
    },
    {
        'title': 'Mixed Dal (Five Lentil Blend)',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 15,
        'cook_time': 35,
        'servings': 6,
        'description': 'Protein-packed five-lentil dal — a nutritional powerhouse.',
        'instructions': (
            '1. Soak lentils 30 minutes; drain.\n'
            '2. Cook with water, turmeric, and salt.\n'
            '3. Prepare tempering with oil, cumin, onion, garlic, tomato.\n'
            '4. Add tempering to dal; simmer 10 minutes.\n'
            '5. Adjust consistency; garnish and serve.'
        ),
        'ingredients': [
            ('Red Lentils (Masoor Dal)', 60),
            ('Moong Dal (Split Mung Beans)', 60),
            ('Toor Dal (Pigeon Peas)', 60),
            ('Green Lentils', 60),
            ('Onion', 100),
            ('Tomato', 100),
            ('Ghee (Clarified Butter)', 15),
            ('Cumin Seeds (Jeera)', 5),
            ('Garlic', 10),
            ('Turmeric Powder', 3),
            ('Salt', 5),
            ('Coriander Leaves (Cilantro)', 10),
        ],
    },
    {
        'title': 'Coconut Vegetable Curry',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 10,
        'cook_time': 25,
        'servings': 4,
        'description': 'Creamy coconut-milk curry with seasonal vegetables.',
        'instructions': (
            '1. Sauté onion, garlic, and ginger in oil.\n'
            '2. Add spices; toast 1 minute.\n'
            '3. Add vegetables; cook 5 minutes.\n'
            '4. Pour in coconut milk; simmer 15 minutes.\n'
            '5. Add tamarind; season and serve with rice.'
        ),
        'ingredients': [
            ('Coconut Milk', 200),
            ('Sweet Potato', 150),
            ('Cauliflower', 150),
            ('Green Peas', 100),
            ('Onion', 100),
            ('Tomato', 100),
            ('Olive Oil', 15),
            ('Garlic', 10),
            ('Ginger (Fresh)', 10),
            ('Cumin Seeds (Jeera)', 5),
            ('Turmeric Powder', 3),
            ('Tamarind', 10),
            ('Salt', 4),
        ],
    },
    {
        'title': 'Iron Boost Trail Mix',
        'diet_type': 'vegan',
        'meal_type': 'snack',
        'prep_time': 5,
        'cook_time': 0,
        'servings': 4,
        'description': 'Nutrient-dense snack of seeds and nuts packed with iron and zinc.',
        'instructions': (
            '1. Combine all ingredients in a bowl.\n'
            '2. Toast lightly if desired.\n'
            '3. Portion into 4 servings and store in airtight container.'
        ),
        'ingredients': [
            ('Pumpkin Seeds', 60),
            ('Sesame Seeds (Til)', 40),
            ('Almonds', 60),
            ('Sunflower Seeds', 40),
            ('Flax Seeds (Linseed)', 20),
            ('Peanuts', 60),
        ],
    },
    {
        'title': 'Greek Yogurt Parfait',
        'diet_type': 'vegetarian',
        'meal_type': 'snack',
        'prep_time': 5,
        'cook_time': 0,
        'servings': 1,
        'description': 'Protein and calcium-rich layered snack with yogurt, nuts, and fruit.',
        'instructions': (
            '1. Layer Greek yogurt in a glass.\n'
            '2. Add sliced banana and almonds.\n'
            '3. Top with chia seeds and flax seeds.\n'
            '4. Serve immediately or refrigerate.'
        ),
        'ingredients': [
            ('Greek Yogurt (Full-fat)', 150),
            ('Banana', 80),
            ('Almonds', 20),
            ('Chia Seeds', 10),
            ('Flax Seeds (Linseed)', 10),
        ],
    },
    {
        'title': 'Nutritional Yeast Pasta',
        'diet_type': 'vegan',
        'meal_type': 'dinner',
        'prep_time': 5,
        'cook_time': 15,
        'servings': 2,
        'description': 'B12-rich vegan pasta with nutritional yeast sauce, spinach, and garlic.',
        'instructions': (
            '1. Cook pasta until al dente.\n'
            '2. Heat olive oil; sauté garlic.\n'
            '3. Add spinach; cook until wilted.\n'
            '4. Add nutritional yeast and pasta water; stir to form sauce.\n'
            '5. Toss pasta with sauce; season and serve.'
        ),
        'ingredients': [
            ('Semolina (Sooji)', 160),
            ('Spinach (Palak)', 100),
            ('Nutritional Yeast', 30),
            ('Olive Oil', 20),
            ('Garlic', 15),
            ('Lemon Juice', 15),
            ('Salt', 4),
        ],
    },
]


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Seed the database with ingredients, recipes, and demo data.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('🌱 Sproutly seed_data starting...'))
        with transaction.atomic():
            ing_map = self._seed_ingredients()
            self._seed_recipes(ing_map)
            self._seed_demo_user(ing_map)
        self.stdout.write(self.style.SUCCESS('✅ Seed complete! Run: python manage.py runserver'))

    # ------------------------------------------------------------------
    def _seed_ingredients(self) -> dict:
        """Create/update ingredients; return name→instance map."""
        ing_map = {}
        for data in INGREDIENTS:
            is_staple = data.pop('is_staple', False)
            ing, created = Ingredient.objects.update_or_create(
                name=data['name'],
                defaults={**data, 'is_staple': is_staple},
            )
            if data.get('is_staple') is None:
                # re-add after pop
                ing.is_staple = is_staple
                ing.save(update_fields=['is_staple'])
            ing_map[data['name']] = ing
            status = 'created' if created else 'updated'
            self.stdout.write(f'  Ingredient {status}: {ing.name}')

        self.stdout.write(self.style.SUCCESS(f'  → {len(ing_map)} ingredients ready.'))
        return ing_map

    # ------------------------------------------------------------------
    def _seed_recipes(self, ing_map: dict):
        for rdata in RECIPES:
            ing_list = rdata.pop('ingredients')
            recipe, created = Recipe.objects.get_or_create(
                title=rdata['title'],
                defaults={**rdata, 'is_public': True},
            )
            if not created:
                # Update fields
                for k, v in rdata.items():
                    setattr(recipe, k, v)
                recipe.save()

            # Re-create ingredients
            recipe.recipe_ingredients.all().delete()
            for ing_name, grams in ing_list:
                ingredient = ing_map.get(ing_name)
                if ingredient:
                    RecipeIngredient.objects.create(
                        recipe=recipe,
                        ingredient=ingredient,
                        quantity_grams=Decimal(str(grams)),
                        display_text='',
                    )
                else:
                    self.stdout.write(self.style.WARNING(f'    Missing ingredient: {ing_name}'))

            # Compute nutrition
            from nutrition.services import save_recipe_nutrition
            save_recipe_nutrition(recipe)

            status = 'created' if created else 'updated'
            self.stdout.write(f'  Recipe {status}: {recipe.title}')

        self.stdout.write(self.style.SUCCESS(f'  → {len(RECIPES)} recipes ready.'))

    # ------------------------------------------------------------------
    def _seed_demo_user(self, ing_map: dict):
        from tracker.models import Favorite
        from nutrition.services import save_recipe_nutrition

        # We set up demo accounts: 'demo' (demo12345) and 'sprout' (sprout123)
        for uname, passw in [('demo', 'demo12345'), ('sprout', 'sprout123')]:
            user, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'email': f'{uname}@sproutly.app',
                    'first_name': uname.title(),
                    'is_active': True,
                },
            )
            user.set_password(passw)
            user.save()
            status = 'Created' if created else 'Updated'
            self.stdout.write(f'  {status} demo user: {uname} / {passw}')

            # Ensure default nutrition goals
            create_default_goals(user)

            # 1. Seed custom user recipes authored by this user
            user_recipes_data = [
                {
                    'title': f"{uname.title()}'s High-Protein Tofu Power Bowl",
                    'diet_type': 'vegan',
                    'meal_type': 'lunch',
                    'prep_time': 10,
                    'cook_time': 15,
                    'servings': 1,
                    'description': 'A delicious personal bowl loaded with marinated crisp tofu, edamame, and sesame brown rice.',
                    'instructions': '1. Cube tofu and sear in olive oil until golden.\n2. Layer over warm brown rice and steamed greens.\n3. Drizzle with tamari and sesame seeds.',
                    'ingredients': [
                        ('Tofu (Firm)', 150),
                        ('Brown Rice', 100),
                        ('Spinach (Palak)', 80),
                        ('Olive Oil', 10),
                    ],
                },
                {
                    'title': f"{uname.title()}'s Morning Golden Cheela",
                    'diet_type': 'vegan',
                    'meal_type': 'breakfast',
                    'prep_time': 10,
                    'cook_time': 10,
                    'servings': 2,
                    'description': 'Savory crisp yellow moong crepes packed with ginger, cumin, and fresh herbs.',
                    'instructions': '1. Blend soaked yellow moong with ginger and green chillies into a smooth batter.\n2. Ladle onto a hot griddle and cook with olive oil until crisp on both sides.\n3. Serve with mint chutney.',
                    'ingredients': [
                        ('Moong Dal (Split Mung Beans)', 100),
                        ('Ginger (Fresh)', 5),
                        ('Olive Oil', 8),
                    ],
                },
            ]

            for ur_data in user_recipes_data:
                recipe, _ = Recipe.objects.update_or_create(
                    author=user,
                    title=ur_data['title'],
                    defaults={
                        'diet_type': ur_data['diet_type'],
                        'meal_type': ur_data['meal_type'],
                        'prep_time': ur_data['prep_time'],
                        'cook_time': ur_data['cook_time'],
                        'servings': ur_data['servings'],
                        'description': ur_data['description'],
                        'instructions': ur_data['instructions'],
                        'is_public': True,
                    },
                )
                recipe.recipe_ingredients.all().delete()
                for ing_name, grams in ur_data['ingredients']:
                    ing = ing_map.get(ing_name)
                    if ing:
                        RecipeIngredient.objects.create(
                            recipe=recipe,
                            ingredient=ing,
                            quantity_grams=Decimal(str(grams)),
                            display_text='',
                        )
                save_recipe_nutrition(recipe)

            # 2. Seed Favorites for user
            fav_titles = [
                'Palak Tofu',
                'Tomato Dal',
                'Overnight Oats with Chia',
                'Quinoa Buddha Bowl',
                'Paneer Bhurji',
                'Rajma Masala',
                'Dal tadka',
            ]
            Favorite.objects.filter(user=user).delete()
            for ftitle in fav_titles:
                r = Recipe.objects.filter(title__iexact=ftitle).first()
                if r:
                    Favorite.objects.get_or_create(user=user, recipe=r)

            # 3. Seed 7 days of meal logs ending today
            today = date.today()
            plans = [
                (0,  _today_plan()),
                (-1, _yesterday_plan()),
                (-2, _two_days_ago_plan()),
                (-3, _three_days_ago_plan()),
                (-4, _four_days_ago_plan()),
                (-5, _five_days_ago_plan()),
                (-6, _six_days_ago_plan()),
            ]
            for offset, day_plan in plans:
                day = today + timedelta(days=offset)
                MealLog.objects.filter(user=user, date=day).delete()
                for meal_type, recipe_title, servings_val in day_plan:
                    recipe = Recipe.objects.filter(title__iexact=recipe_title).first()
                    if recipe:
                        log_meal(
                            user=user,
                            date_val=day,
                            meal_type=meal_type,
                            recipe=recipe,
                            servings=Decimal(str(servings_val)),
                        )
                    else:
                        self.stdout.write(self.style.WARNING(f'    Log skipped - recipe not found: {recipe_title}'))

        self.stdout.write(self.style.SUCCESS('  → Demo accounts (demo & sprout) fully fed with 7-day logs, favorites, and recipes.'))


def _today_plan():
    # Exactly matches user tracker mockup (media_1795105332747_4ee057c7.jpg)
    return [
        ('breakfast', 'Oats with soy milk', 1),
        ('lunch',     'Dal tadka',          Decimal('1.5')),
        ('lunch',     'Steamed rice',       1),
        ('snack',     'Roasted chana',      Decimal('0.5')),
    ]


def _yesterday_plan():
    return [
        ('breakfast', 'Poha (Flattened Rice Breakfast)', 1),
        ('breakfast', 'High-Protein Smoothie Bowl',      1),
        ('lunch',     'Quinoa Buddha Bowl',              1),
        ('dinner',    'Spinach & Tofu Curry',            1),
        ('snack',     'Greek Yogurt Parfait',            1),
    ]


def _two_days_ago_plan():
    return [
        ('breakfast', 'Paneer Bhurji',                   1),
        ('lunch',     'Rajma Chawal',                    1),
        ('dinner',    'Mixed Dal (Five Lentil Blend)',   1),
        ('snack',     'Chia Pudding',                    1),
    ]


def _three_days_ago_plan():
    return [
        ('breakfast', 'Overnight Oats with Chia',        1),
        ('lunch',     'Palak Tofu',                      1),
        ('dinner',    'Tomato Dal',                      1),
        ('snack',     'Iron Boost Trail Mix',            1),
    ]


def _four_days_ago_plan():
    return [
        ('breakfast', 'Moong Dal Cheela',                1),
        ('lunch',     'Chana Bowl',                      1),
        ('dinner',    'Soybean Keema Matar',             1),
        ('snack',     'Roasted chana',                   1),
    ]


def _five_days_ago_plan():
    return [
        ('breakfast', 'Chia Berry Parfait',              1),
        ('lunch',     'Moroccan Lentil Stew',            1),
        ('dinner',    'Palak Paneer',                    1),
        ('snack',     'Greek Yogurt Parfait',            1),
    ]


def _six_days_ago_plan():
    return [
        ('breakfast', 'Tofu Scramble',                   1),
        ('lunch',     'Quinoa Bowl',                     1),
        ('dinner',    'Rajma Masala',                    1),
        ('snack',     'Chia Pudding',                    1),
    ]

