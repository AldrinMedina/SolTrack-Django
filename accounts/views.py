import uuid
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
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
            if not user.is_approved:
                messages.warning(request, "⚠️ Your account is pending admin approval.")
                return redirect("login")

            # Create a unique session identifier
            session_id = str(uuid.uuid4())
            request.session["session_id"] = session_id
            request.session["user_email"] = user.email
            request.session["user_role"] = user.role
            request.session["login_time"] = timezone.now().isoformat()

            login(request, user)  # Django built-in login

            messages.success(request, f"✅ Welcome back, {user.full_name}!")
            return redirect("overview")  # redirect based on your project
        else:
            messages.error(request, "❌ Invalid email or password.")
            return redirect("login")
    return render(request, "login.html")




# Registration view
def register_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = CustomUser.objects.create_user(
                email=form.cleaned_data['email'],
                full_name=form.cleaned_data['full_name'],
                password=form.cleaned_data['password']
            )
            # user.role = form.cleaned_data.get('role', 'buyer')
            user.m_address = form.cleaned_data.get('m_address')
            user.organization = form.cleaned_data.get('organization')
            user.is_active = True
            user.is_approved = False  # ⛔ requires admin approval
            uploaded_file = request.FILES.get('business_license')
            if uploaded_file:
                user.business_license = uploaded_file.read()
            user.save()

            messages.success(request, "🎉 Account created successfully! Please wait for admin approval before logging in.")
            return redirect("login")
        else:
            messages.error(request, "⚠️ Please fix the errors below.")
    else:
        form = RegistrationForm()
    return render(request, "registration.html", {"form": form})

# Logout view
def logout_view(request):
    logout(request)
    request.session.flush()
    messages.info(request, "👋 You’ve been logged out.")
    return redirect('index')