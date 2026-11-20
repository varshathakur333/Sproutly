"""
accounts/views.py
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages

from accounts.forms import RegisterForm, SproutlyPasswordChangeForm
from nutrition.services import create_default_goals


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            create_default_goals(user)
            login(request, user)
            messages.success(request, f"Welcome to Sproutly, {user.first_name or user.username}! 🌱")
            return redirect('goals')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
    else:
        form = AuthenticationForm()
        for field in form.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    return render(request, 'accounts/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You've been logged out. See you soon! 🌿")
    return redirect('home')


@login_required
def password_change_view(request):
    if request.method == 'POST':
        form = SproutlyPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.success(request, "Password changed successfully.")
            return redirect('goals')
    else:
        form = SproutlyPasswordChangeForm(user=request.user)

    return render(request, 'accounts/password_change.html', {'form': form})

