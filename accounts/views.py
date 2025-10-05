from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib import messages
from .forms import RegistrationForm
from .models import UserProfile

# Create your views here.
def index(request):
    return render(request, 'index.html')

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "✅ Login successful. Welcome back!")
            return redirect("dashboard")  # or wherever
        else:
            messages.error(request, "❌ Invalid username or password.")

    return render(request, "login.html")

def register_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"]
            )
            profile = UserProfile.objects.create(
                user=user,
                middle_name=form.cleaned_data.get("middle_name"),
                phone=form.cleaned_data["phone"],
                organization=form.cleaned_data.get("organization"),
                user_role=form.cleaned_data["user_role"],
                wallet_address=form.cleaned_data.get("wallet_address"),
                id_upload=form.cleaned_data.get("id_upload"),
                address_upload=form.cleaned_data.get("address_upload"),
            )

            messages.success(request, "🎉 Account created successfully! Please log in.")
            login(request, user)  # auto-login after registration
            return redirect("dashboard")  # or wherever
        else:
            messages.error(request, "⚠️ Please fix the errors below.")
    else:
        form = RegistrationForm()

    return render(request, "registration.html", {"form": form})