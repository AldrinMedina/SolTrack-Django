from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from .forms import RegistrationForm
from .models import CustomUser

# Landing page
def index(request):
    return render(request, 'index.html')


# Login view
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "✅ Login successful. Welcome back!")
            return redirect("dashboard")
        else:
            messages.error(request, "❌ Invalid email or password.")

    return render(request, "login.html")



# Registration view
def register_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = CustomUser.objects.create_user(
                email=form.cleaned_data["email"],
                full_name=form.cleaned_data["full_name"],
                password=form.cleaned_data["password"],
                role=form.cleaned_data.get("role", "buyer"),
                organization=form.cleaned_data.get("organization"),
            )
            messages.success(request, "🎉 Account created successfully! Please log in.")
            login(request, user)
            return redirect("dashboard")
        else:
            messages.error(request, "⚠️ Please fix the errors below.")
    else:
        form = RegistrationForm()

    return render(request, "registration.html", {"form": form})
