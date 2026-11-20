"""
nutrition/management/commands/import_usda.py
--------------------------------------------
Optional management command that imports foods from the USDA FoodData Central API.
Requires: USDA_API_KEY set in .env
Idempotent: uses external_id to avoid duplicates.

Usage:
    python manage.py import_usda --query "lentils" --max 20
"""

import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from nutrition.models import Ingredient


USDA_SEARCH_URL = 'https://api.nal.usda.gov/fdc/v1/foods/search'
USDA_FOOD_URL   = 'https://api.nal.usda.gov/fdc/v1/food/{fdcId}'

# FDC nutrient IDs → Sproutly field names
NUTRIENT_MAP = {
    1008: 'calories',   # Energy (kcal)
    1003: 'protein',    # Protein
    1005: 'carbs',      # Carbohydrate, by difference
    1004: 'fat',        # Total lipid (fat)
    1079: 'fiber',      # Fiber, total dietary
    2000: 'sugar',      # Sugars, total
    1089: 'iron',       # Iron, Fe
    1087: 'calcium',    # Calcium, Ca
    1162: 'vitamin_c',  # Vitamin C
    1178: 'b12',        # Vitamin B-12
    1095: 'zinc',       # Zinc, Zn
    1090: 'magnesium',  # Magnesium, Mg
    1093: 'sodium',     # Sodium, Na
}

CATEGORY_MAP = {
    'Legumes and Legume Products': 'legume',
    'Cereal Grains and Pasta':     'grain',
    'Vegetables and Vegetable Products': 'vegetable',
    'Fruits and Fruit Juices':     'fruit',
    'Dairy and Egg Products':      'dairy',
    'Nut and Seed Products':       'nut_seed',
    'Fats and Oils':               'oil',
    'Spices and Herbs':            'spice',
}


class Command(BaseCommand):
    help = 'Import vegetarian ingredients from USDA FoodData Central (requires USDA_API_KEY).'

    def add_arguments(self, parser):
        parser.add_argument('--query', '-q', default='vegetarian',
                            help='Search query (default: vegetarian)')
        parser.add_argument('--max', '-m', type=int, default=50,
                            help='Max number of foods to import')
        parser.add_argument('--category', '-c', default='Foundation',
                            help='FDC data type: Foundation, SR Legacy, Survey (FNDDS)')

    def handle(self, *args, **options):
        api_key = getattr(settings, 'USDA_API_KEY', '').strip()
        if not api_key:
            raise CommandError(
                'USDA_API_KEY is not set. Add it to your .env file. '
                'Get a free key at https://fdc.nal.usda.gov/api-guide.html'
            )

        try:
            import urllib.request
        except ImportError:
            raise CommandError('urllib not available.')

        self.stdout.write(f'Searching USDA FDC for "{options["query"]}"...')
        foods = self._search(api_key, options['query'], options['max'], options['category'])
        self.stdout.write(f'Found {len(foods)} foods. Importing...')

        created = updated = skipped = 0
        for food in foods:
            try:
                ing, was_created = self._import_food(food)
                if ing is None:
                    skipped += 1
                elif was_created:
                    created += 1
                    self.stdout.write(f'  + Created: {ing.name}')
                else:
                    updated += 1
                    self.stdout.write(f'  ~ Updated: {ing.name}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ! Skipped {food.get("description", "?")}: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created: {created}, Updated: {updated}, Skipped: {skipped}'
        ))

    def _search(self, api_key, query, max_results, data_type):
        import urllib.request, urllib.parse, json
        params = urllib.parse.urlencode({
            'api_key': api_key,
            'query':   query,
            'dataType': data_type,
            'pageSize': min(max_results, 200),
        })
        url = f'{USDA_SEARCH_URL}?{params}'
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get('foods', [])[:max_results]

    def _import_food(self, food):
        fdc_id = str(food.get('fdcId', ''))
        if not fdc_id:
            return None, False

        name = food.get('description', '').strip()[:200]
        if not name:
            return None, False

        # Map nutrients
        nutrients = {f: Decimal('0') for f in [
            'calories','protein','carbs','fat','fiber','sugar',
            'iron','calcium','b12','zinc','magnesium','vitamin_c','sodium',
        ]}
        for n in food.get('foodNutrients', []):
            nutrient_id = n.get('nutrientId') or (n.get('nutrient', {}) or {}).get('id')
            field = NUTRIENT_MAP.get(nutrient_id)
            if field:
                try:
                    nutrients[field] = Decimal(str(n.get('value', 0)))
                except Exception:
                    pass

        # Category
        food_cat = food.get('foodCategory', '') or ''
        category = CATEGORY_MAP.get(food_cat, 'other')

        ing, created = Ingredient.objects.update_or_create(
            external_id=fdc_id,
            defaults={
                'name':      name,
                'category':  category,
                'is_vegan':  True,  # user can correct
                **nutrients,
            },
        )
        return ing, created

