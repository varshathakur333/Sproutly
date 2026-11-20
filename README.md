# Sproutly 🌱 — Vegetarian Nutrition & Meal Tracking Web App

> **Eat plants. Hit your numbers.**

Sproutly is a full-stack Django web application designed to help vegetarians reach their daily nutrient targets—with special focus on vegetarian essentials: **Protein**, **Fiber**, **Iron**, **Calcium**, **Vitamin B12**, and **Calories**.

Users browse and filter recipes by nutrient thresholds, match meals against ingredients in their pantry, set personal goals, log meals with real-time portion scaling, and view an interactive live dashboard with Chart.js analytics and smart nutrient gap recommendations.

---

## 🎨 UI & Design

Sproutly features a custom **warm cream and golden sprout** aesthetic:
- **Palette**: Cream background (`#FAF6EE`), sprout greens (`#4A7C2F`, `#2D5016`), sunshine yellow (`#F5C842`), and warm coral (`#E05C3A`).
- **Mascot**: **Sprig** 🌱, the friendly potted plant mascot who cheers on progress.
- **Components**: Pill-shaped controls (`border-radius: 9999px`), responsive grid cards, interactive Chart.js charts, live portion steppers, and toast notifications.
- **Mobile-first**: Sticky desktop navbar with quick "+ Log a meal" action, plus mobile bottom tab bar (Recipes, Tracker, Dashboard, Goals).

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+
- Virtual environment (recommended)

### 2. Installation & Setup
```bash
# Clone or navigate to the repository
cd Sproutly-django

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Seed database with 58+ vegetarian ingredients, 26 recipes, and demo user with 3 days of logs
python manage.py seed_data

# Start development server
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

---

## 👤 Demo Account

| Username | Password | Notes |
|:---|:---|:---|
| `demo` | `demo12345` | Pre-populated with default goals and 3 days of meal logs for instant dashboard visualization. |

You can also register a brand new account at `/accounts/register/`, which will automatically initialize default vegetarian nutrient goals.

---

## 📑 Pages & Features

| # | Page | URL | Access | Highlights |
|:---|:---|:---|:---|:---|
| 1 | **Home** | `/` | Public | Hero section with Sprig mascot, 3 feature cards, and 6 featured high-protein vegetarian recipes. |
| 2 | **Register** | `/accounts/register/` | Public | Yellow card signup form with inline validation. Auto-creates default goals and redirects to Goals page. |
| 3 | **Login** | `/accounts/login/` | Public | Welcoming login form featuring Sprig. Redirects to Dashboard on success. |
| 4 | **Recipe List** | `/recipes/` | Public | Filter sidebar with live debounced search, diet badges, presets (High Protein, Iron Rich, Low Calorie, High Fiber), nutrient range sliders, "Ingredients I have" pantry tag matcher with missing ingredient tags, tabs (All / My Recipes / Favorites), and pagination. |
| 5 | **Recipe Detail** | `/recipes/<slug>/` | Public | Recipe description, ingredients, step-by-step instructions, interactive servings multiplier that dynamically scales ingredients and nutrients, 1-click Add to Log, Favorite button, and author Edit/Delete (with confirmation modal). |
| 6 | **Recipe Form** | `/recipes/new/`, `/recipes/<slug>/edit/` | Login | Create and edit recipes with dynamic ingredient formset, autocomplete, live per-serving nutrition preview, and "Enter nutrition manually" toggle. Author-only permissions. |
| 7 | **Meal Tracker** | `/tracker/?date=YYYY-MM-DD` | Login | Date navigation (`< Prev`, `Next >`, date picker), grouped by meal (Breakfast, Lunch, Dinner, Snack), quick-add food search, instant 0.25-step portion steppers (via PATCH), row delete, duplicate to another date, and sticky calories & protein totals bar. |
| 8 | **Dashboard** | `/dashboard/?date=YYYY-MM-DD` | Login | Real-time progress bars with color states (Red <50%, Amber 50-90%, Green 90-110%, Blue >110%), summary gap sentence, Macro Split donut chart, Calories by Meal bar chart, 7-day trend line chart with nutrient switcher, and "Recommended for you" gap-closing recipe recommendations. |
| 9 | **Goals** | `/goals/` | Login | Customize daily nutrient targets and minimum/maximum directions, "Reset to defaults" action, and integrated password change form. |

---

## 🛠 Tech Stack

- **Backend**: Python 3.11+, Django 5.x / 6.x, Django ORM, Django Forms, Django REST Framework
- **Database**: SQLite in development, PostgreSQL-ready via `DATABASE_URL` (`dj-database-url`)
- **Frontend**: Django Templates, Custom CSS (`sproutly.css` with CSS variables & responsive grid/flexbox), Vanilla JavaScript (`sproutly.js` with `fetch` API), Chart.js
- **Configuration & Static**: `django-environ`, `whitenoise`
- **Testing**: Django `TestCase` (66 comprehensive unit & integration tests)

---

## 🧮 Nutrient Calculation & Logic

All business logic resides in dedicated `services.py` modules:
1. **Recipe per-serving nutrition**:
   $$\text{Per-Serving Nutrient} = \frac{\sum (\text{Ingredient Per 100g} \times \frac{\text{Quantity (g)}}{100})}{\text{Servings}}$$
2. **Logged nutrient**:
   $$\text{Log Snapshot} = \text{Recipe Per-Serving} \times \text{Servings Logged}$$
   Stored as immutable snapshots on `MealLog` rows for historical accuracy.
3. **Pantry Matching**:
   $$\text{Match Score} = \frac{\text{Matched Non-Staple Ingredients}}{\text{Total Non-Staple Ingredients}}$$
   Common staples (oil, salt, water, basic spices) are automatically excluded so pantry matches reflect real recipes.
4. **Recommendation Scoring**:
   Recipes are scored based on how efficiently one serving closes the user's remaining daily nutrient gaps (weighted by urgency, penalized if exceeding remaining calorie limits).

---

## 🌐 REST API Endpoints

The frontend AJAX interactions seamlessly interact with the Django REST Framework endpoints:

- `GET /api/recipes/` — Filter and search recipes (supports `q`, `diet_type`, `meal_type`, `protein_min`, `iron_min`, `cal_min`, `have_ids`, `sort`, etc.)
- `POST /api/recipes/` — Create new recipe (authenticated)
- `GET /api/recipes/<id>/` — Recipe detail with full nutrition breakdown
- `POST /api/recipes/<id>/favorite/` — Toggle recipe favorite
- `POST /api/recipes/preview_nutrition/` — Live preview nutrition for unsaved recipe ingredients
- `GET /api/ingredients/?q=` — Autocomplete ingredient search
- `GET /api/search/?q=` — Unified food search across recipes and ingredients
- `GET, PUT /api/goals/` — View or update user goals
- `POST /api/goals/reset_defaults/` — Reset user goals to standard defaults
- `GET, POST /api/logs/?date=YYYY-MM-DD` — List and create meal logs
- `PATCH, DELETE /api/logs/<id>/` — Update servings or delete meal log
- `POST /api/logs/<id>/copy/` — Duplicate meal log to another meal or date
- `GET /api/dashboard/?date=YYYY-MM-DD` — Dashboard metrics, totals, and progress
- `GET /api/recommendations/?date=YYYY-MM-DD` — Smart recipe recommendations
- `GET /api/trend/?date=YYYY-MM-DD` — 7-day trend series data

---

## 🌾 Optional USDA FoodData Central Import

To import ingredients directly from the official USDA FoodData Central API:
1. Obtain a free API key at [USDA FoodData Central](https://fdc.nal.usda.gov/api-guide.html).
2. Add your key to `.env`:
   ```env
   USDA_API_KEY=your_usda_api_key_here
   ```
3. Run the management command:
   ```bash
   python manage.py import_usda --query "lentils" --max 30
   ```
The command is idempotent and updates or creates ingredients keyed by their USDA `external_id`.

---

## 🧪 Running Tests

Execute the automated test suite covering calculation math, filtering, recommendations, and data isolation:

```bash
python manage.py test nutrition recipes tracker
```
*Current test suite: **66 tests passed**, 0 failures.*

---

## 📂 Project Architecture

```
Sproutly-django/
├── config/                         # Core Django settings, URLs, WSGI
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── accounts/                       # Authentication, registration, password forms
│   ├── forms.py
│   ├── urls.py
│   └── views.py
├── nutrition/                      # Ingredients, goals, and nutrition computation
│   ├── models.py
│   ├── services.py                 # Pure calculation & progress logic
│   ├── admin.py
│   ├── tests.py
│   └── management/commands/
│       ├── seed_data.py            # 58+ ingredients, 26 recipes, demo user
│       └── import_usda.py          # USDA FDC API importer
├── recipes/                        # Recipe catalog, dynamic forms, and pantry search
│   ├── models.py
│   ├── forms.py
│   ├── services.py                 # Query filtering & ingredient match scoring
│   ├── views.py
│   ├── urls.py
│   └── tests.py
├── tracker/                        # Meal logging, dashboard, and recommendations
│   ├── models.py
│   ├── services.py                 # Daily totals & recommendation engine
│   ├── views.py
│   ├── urls.py
│   └── tests.py
├── api/                            # Django REST Framework API layer
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── templates/                      # HTML5 templates matching design specs
│   ├── base.html                   # Sticky navbar, Sprig SVG, bottom tab bar
│   ├── home.html                   # Hero, feature highlights, featured recipes
│   ├── accounts/
│   │   ├── login.html              # Yellow card login
│   │   ├── register.html           # Yellow card signup
│   │   └── password_change.html
│   ├── recipes/
│   │   ├── recipe_list.html        # Card grid & sidebar drawer filters
│   │   ├── recipe_detail.html      # Detail view with interactive scaler
│   │   └── recipe_form.html        # Recipe creation with live nutrition preview
│   ├── tracker/
│   │   ├── tracker.html            # Meal logger with 0.25 stepper controls
│   │   ├── dashboard.html          # Progress rings, Chart.js charts & recos
│   │   └── goals.html              # Goal target & min/max toggles
│   └── partials/
│       ├── _recipe_card.html
│       ├── _nutrient_bar.html
│       ├── _log_row.html
│       └── _toast.html
├── static/
│   ├── css/sproutly.css            # Custom CSS variables, responsive layout
│   └── js/sproutly.js              # Fetch client, autocompletes, steppers
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔒 Security & Data Isolation

- **CSRF Protection**: Applied to all form submissions and AJAX requests via the `X-CSRFToken` header.
- **Data Isolation**: Verified by automated test cases ensuring users cannot view or modify another user's logs, private recipes, or goals.
- **File Validation**: Image uploads restricted to `.jpg`, `.jpeg`, `.png`, `.webp` and limited to 2 MB.
- **ORM Optimization**: Heavy use of `select_related` and `prefetch_related` across list, detail, dashboard, and tracker queries.

