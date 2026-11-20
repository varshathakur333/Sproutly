"""
recipes/forms.py
Forms and formsets for recipes and ingredients.
"""

from decimal import Decimal
from django import forms
from django.forms import formset_factory

from recipes.models import Recipe, RecipeIngredient, RecipeNutrition
from nutrition.models import Ingredient
from nutrition.services import NUTRIENT_FIELDS


class RecipeForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = [
            'title', 'description', 'instructions', 'image',
            'prep_time', 'cook_time', 'servings',
            'diet_type', 'meal_type', 'is_public',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Smoky Lentil Soup'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'A short description…'}),
            'instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 8, 'placeholder': 'Step 1: …\nStep 2: …'}),
            'prep_time': forms.NumberInput(attrs={'class': 'form-control form-control--pill', 'min': 0, 'placeholder': '10'}),
            'cook_time': forms.NumberInput(attrs={'class': 'form-control form-control--pill', 'min': 0, 'placeholder': '30'}),
            'servings': forms.NumberInput(attrs={'class': 'form-control form-control--pill', 'min': 1, 'id': 'servings-input'}),
            'diet_type': forms.Select(attrs={'class': 'form-control'}),
            'meal_type': forms.Select(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'image' in self.fields:
            self.fields['image'].widget.attrs.update({'class': 'form-control', 'accept': 'image/*'})


class RecipeNutritionManualForm(forms.Form):
    calories   = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    protein    = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    carbs      = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    fat        = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    fiber      = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    sugar      = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    iron       = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    calcium    = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    b12        = forms.DecimalField(required=False, min_value=0, decimal_places=4, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.01'}))
    zinc       = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    magnesium  = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    vitamin_c  = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))
    sodium     = forms.DecimalField(required=False, min_value=0, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control form-control--pill nutrition-manual-input', 'step': '0.1'}))


class IngredientRowForm(forms.Form):
    id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    ingredient = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control--pill ingredient-autocomplete',
            'placeholder': 'Ingredient name…',
            'autocomplete': 'off',
        })
    )
    grams = forms.DecimalField(
        required=False,
        min_value=Decimal('0.01'),
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control--pill ingredient-grams',
            'placeholder': 'g',
            'min': '0',
            'step': '0.1',
        })
    )
    display_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control--pill',
            'placeholder': 'e.g. 1 cup chickpeas',
        })
    )
    DELETE = forms.BooleanField(required=False, widget=forms.HiddenInput())


IngredientFormSet = formset_factory(IngredientRowForm, extra=1, can_delete=True)

