"""
recipes/views.py
Views for browsing, searching, creating, editing, and deleting recipes.
"""

from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, Http404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction

from recipes.models import Recipe, RecipeIngredient, RecipeNutrition
from nutrition.models import Ingredient
from tracker.models import Favorite
from recipes.forms import RecipeForm, IngredientFormSet, RecipeNutritionManualForm
from recipes.services import filter_recipes, sort_recipes, annotate_match_data
from nutrition.services import save_recipe_nutrition, NUTRIENT_FIELDS


def _count_active_filters(params: dict) -> int:
    """Count how many filter criteria are actively applied."""
    count = 0
    if params.get('q', '').strip():
        count += 1
    if params.get('preset'):
        count += 1
    if params.get('diet_type'):
        count += 1
    if params.get('meal_type'):
        count += 1
    max_prep = params.get('max_prep_time')
    if max_prep and str(max_prep).strip() and str(max_prep).strip() not in ('60', '0'):
        count += 1
    if params.get('cal_min') or params.get('cal_max') or params.get('calories_min') or params.get('calories_max'):
        count += 1
    if params.get('protein_min') or params.get('protein_max'):
        count += 1
    if params.get('iron_min') or params.get('iron_max'):
        count += 1
    if params.get('fiber_min') or params.get('fiber_max'):
        count += 1
    if params.get('sort') and params.get('sort') != 'newest':
        count += 1
    if params.get('tab') in ['mine', 'favorites']:
        count += 1
    return count


def recipe_list(request):
    """
    Recipe list view supporting:
    - Text search
    - Diet type, meal type, max prep time
    - Nutrient ranges (calories, protein, iron, fiber, etc.)
    - Presets (High Protein, Iron Rich, Low Calorie, High Fiber)
    - Ingredients I have
    - Tabs (All, My Recipes, Favorites)
    - Sort options
    - Pagination (16 per page for 4-column neo grid)
    """
    params = dict(request.GET)
    # Flatten single items from QueryDict
    flat_params = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in params.items()}

    # Map template query param names to service filter param names if needed
    if 'cal_min' in flat_params and 'calories_min' not in flat_params:
        flat_params['calories_min'] = flat_params['cal_min']
    if 'cal_max' in flat_params and 'calories_max' not in flat_params:
        flat_params['calories_max'] = flat_params['cal_max']

    # Handle ingredients I have
    have_ingredients = flat_params.get('have_ingredients', '')
    have_ids = []
    if have_ingredients:
        have_ids = [int(i.strip()) for i in str(have_ingredients).split(',') if i.strip().isdigit()]
        flat_params['have_ids'] = have_ids

    # QuerySet filtering
    qs = filter_recipes(flat_params, user=request.user)

    # Sort
    sort_key = flat_params.get('sort', 'newest')
    if sort_key == 'cal_asc':
        sort_key = 'calories_asc'
    elif sort_key == 'best_match':
        sort_key = 'match_score'

    results = sort_recipes(qs, sort_key, have_ids=have_ids)
    if have_ids and isinstance(results, list):
        annotate_match_data(results, have_ids)

    # Pagination (16 per page for 4-column neo grid)
    paginator = Paginator(results, 16)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    active_filters_count = _count_active_filters(flat_params)

    context = {
        'recipes': page_obj.object_list,
        'page_obj': page_obj,
        'diet_choices': Recipe.DIET_CHOICES,
        'meal_choices': [c for c in Recipe.MEAL_TYPE_CHOICES if c[0] != 'any'],
        'active_filters_count': active_filters_count,
    }
    return render(request, 'recipes/recipe_list.html', context)


def recipe_detail(request, slug):
    """
    Recipe detail view with live scaling and logging functionality.
    """
    recipe = get_object_or_404(
        Recipe.objects.select_related('author', 'nutrition').prefetch_related(
            'recipe_ingredients__ingredient'
        ),
        slug=slug
    )

    # Permission check for private recipes
    if not recipe.is_public and (not request.user.is_authenticated or recipe.author != request.user):
        raise Http404("Recipe not found.")

    is_favorited = False
    if request.user.is_authenticated:
        is_favorited = Favorite.objects.filter(user=request.user, recipe=recipe).exists()

    context = {
        'recipe': recipe,
        'is_favorited': is_favorited,
    }
    return render(request, 'recipes/recipe_detail.html', context)


@login_required
def recipe_create(request):
    """
    Create a new recipe with dynamic ingredient rows and optional manual nutrition.
    """
    if request.method == 'POST':
        form = RecipeForm(request.POST, request.FILES)
        ingredient_formset = IngredientFormSet(request.POST, prefix='ingredients')
        nutrition_form = RecipeNutritionManualForm(request.POST, prefix='nutrition')

        if form.is_valid() and ingredient_formset.is_valid():
            with transaction.atomic():
                recipe = form.save(commit=False)
                recipe.author = request.user
                recipe.save()

                for ing_data in ingredient_formset.cleaned_data:
                    if not ing_data or ing_data.get('DELETE'):
                        continue
                    ing_name = ing_data.get('ingredient', '').strip()
                    grams = ing_data.get('grams')
                    display_text = ing_data.get('display_text', '').strip()

                    if ing_name:
                        if not grams or grams <= 0:
                            grams = Decimal('50')
                        if not display_text:
                            display_text = f"{int(grams)}g"
                        ingredient = Ingredient.objects.filter(name__iexact=ing_name).first()
                        if not ingredient:
                            ingredient = Ingredient.objects.create(
                                name=ing_name,
                                category='other',
                                is_vegan=(recipe.diet_type == 'vegan')
                            )
                        RecipeIngredient.objects.create(
                            recipe=recipe,
                            ingredient=ingredient,
                            quantity_grams=grams,
                            display_text=display_text,
                        )

                # Check if manual nutrition was entered
                has_manual = False
                manual_dict = {}
                if nutrition_form.is_valid():
                    for f in NUTRIENT_FIELDS:
                        val = nutrition_form.cleaned_data.get(f)
                        if val is not None and val > 0:
                            has_manual = True
                            manual_dict[f] = val

                if has_manual:
                    save_recipe_nutrition(recipe, manual_data=manual_dict)
                else:
                    save_recipe_nutrition(recipe)

            messages.success(request, f"Recipe '{recipe.title}' created successfully! 🌱")
            return redirect('recipe_detail', slug=recipe.slug)
    else:
        form = RecipeForm(initial={'servings': 1, 'is_public': True})
        ingredient_formset = IngredientFormSet(prefix='ingredients')
        nutrition_form = RecipeNutritionManualForm(prefix='nutrition')

    context = {
        'form': form,
        'ingredient_formset': ingredient_formset,
        'nutrition_form': nutrition_form,
        'recipe': None,
    }
    return render(request, 'recipes/recipe_form.html', context)


@login_required
def recipe_edit(request, slug):
    """
    Edit an existing recipe and its ingredients.
    """
    recipe = get_object_or_404(Recipe, slug=slug)
    if recipe.author != request.user:
        return HttpResponseForbidden("You cannot edit recipes you did not create.")

    if request.method == 'POST':
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        ingredient_formset = IngredientFormSet(request.POST, prefix='ingredients')
        nutrition_form = RecipeNutritionManualForm(request.POST, prefix='nutrition')

        if form.is_valid() and ingredient_formset.is_valid():
            with transaction.atomic():
                recipe = form.save()

                # Recreate recipe ingredients
                recipe.recipe_ingredients.all().delete()
                for ing_data in ingredient_formset.cleaned_data:
                    if not ing_data or ing_data.get('DELETE'):
                        continue
                    ing_name = ing_data.get('ingredient', '').strip()
                    grams = ing_data.get('grams')
                    display_text = ing_data.get('display_text', '').strip()

                    if ing_name:
                        if not grams or grams <= 0:
                            grams = Decimal('50')
                        if not display_text:
                            display_text = f"{int(grams)}g"
                        ingredient = Ingredient.objects.filter(name__iexact=ing_name).first()
                        if not ingredient:
                            ingredient = Ingredient.objects.create(
                                name=ing_name,
                                category='other',
                                is_vegan=(recipe.diet_type == 'vegan')
                            )
                        RecipeIngredient.objects.create(
                            recipe=recipe,
                            ingredient=ingredient,
                            quantity_grams=grams,
                            display_text=display_text,
                        )

                # Check manual nutrition
                has_manual = False
                manual_dict = {}
                if nutrition_form.is_valid():
                    for f in NUTRIENT_FIELDS:
                        val = nutrition_form.cleaned_data.get(f)
                        if val is not None and val > 0:
                            has_manual = True
                            manual_dict[f] = val

                if has_manual:
                    save_recipe_nutrition(recipe, manual_data=manual_dict)
                else:
                    save_recipe_nutrition(recipe)

            messages.success(request, f"Recipe '{recipe.title}' updated! 🌿")
            return redirect('recipe_detail', slug=recipe.slug)
    else:
        form = RecipeForm(instance=recipe)
        initial_ingredients = [
            {
                'id': ri.id,
                'ingredient': ri.ingredient.name,
                'grams': ri.quantity_grams,
                'display_text': ri.display_text,
            }
            for ri in recipe.recipe_ingredients.select_related('ingredient').all()
        ]
        ingredient_formset = IngredientFormSet(
            initial=initial_ingredients,
            prefix='ingredients'
        )

        initial_nutrition = {}
        if hasattr(recipe, 'nutrition') and recipe.nutrition.is_manual:
            for f in NUTRIENT_FIELDS:
                initial_nutrition[f] = getattr(recipe.nutrition, f, 0)
        nutrition_form = RecipeNutritionManualForm(initial=initial_nutrition, prefix='nutrition')

    context = {
        'form': form,
        'ingredient_formset': ingredient_formset,
        'nutrition_form': nutrition_form,
        'recipe': recipe,
    }
    return render(request, 'recipes/recipe_form.html', context)


@login_required
def recipe_delete(request, slug):
    """
    Delete a recipe (author only). Uses POST confirmation from detail page modal.
    """
    recipe = get_object_or_404(Recipe, slug=slug)
    if recipe.author != request.user:
        return HttpResponseForbidden("You cannot delete recipes you did not create.")

    if request.method == 'POST':
        title = recipe.title
        recipe.delete()
        messages.success(request, f"Recipe '{title}' was deleted.")
        return redirect('recipe_list')

    return redirect('recipe_detail', slug=slug)
