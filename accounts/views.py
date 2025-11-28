import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.conf import settings
from django.core import signing
from django.utils import timezone
from django.urls import reverse
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.auth.hashers import make_password

import geopy
import requests

import time
from .supabase_client import supabase
from .forms import BuyerUserForm, SellerUserForm, BuyerOrgForm, SellerOrgForm
from .models import CustomUser, PendingUser

# Token salt
TOKEN_SALT = 'soltrack-registration-salt'
TOKEN_MAX_AGE = 3600  # 1 hour in seconds

def _site_url():
    return getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')

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
            request.session["user_id"] = user.user_id
            request.session["user_email"] = user.email
            request.session["user_role"] = user.role
            request.session["m_address"] = user.m_address
            request.session["user_latitude"] = user.latitude
            request.session["user_longitude"] = user.longitude
            request.session["login_time"] = timezone.now().isoformat()
            request.session["user_PK"] = user.private_key
            login(request, user)  # Django built-in login

            messages.success(request, f"✅ Welcome back, {user.full_name}!")
            if user.role == "Admin":
                return redirect("admin_dashboard")
            elif user.role == "Seller":
                return redirect("overview")  # Change to your actual seller view
            elif user.role == "Buyer":
                return redirect("overview")  # Your main buyer page
            else:
                return redirect("overview")
            # return redirect("overview")  # redirect based on your project
        else:
            messages.error(request, "❌ Invalid email or password.")
            return redirect("login")
    return render(request, "login.html")




# Registration view
# Step 1: Choose role
def choose_role_view(request):
    return render(request, 'registration_choose_role.html')


# Step 2: User info (creates PendingUser and sends verification email)
def register_user_info(request, role):
    role = role.lower()
    if role not in ('buyer', 'seller'):
        messages.error(request, "Invalid role selected.")
        return redirect('choose_role')

    form_class = BuyerUserForm if role == 'buyer' else SellerUserForm

    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            # Hash password for safe storage in pending_user
            hashed_pw = make_password(data['password'])

            # Create PendingUser row
            pending = PendingUser(
                name=data['full_name'],
                email=data['email'],
                password=hashed_pw,
                role=role
            )

            # generate token and save
            token_payload = {'pending_id': None, 'email': data['email']}
            # save without token first to get id if table uses serial PK
            # we will save token after saving row
            # Because model has managed=False, we still can .save()
            pending.token = ''  # placeholder
            pending.save()

            token_payload['pending_id'] = pending.id
            token = signing.dumps(token_payload, salt=TOKEN_SALT)
            pending.token = token
            pending.save()

            # Send verification email
            verify_path = reverse('verify_email', kwargs={'token': token})
            verify_link = _site_url().rstrip('/') + verify_path

            subject = "Verify your SolTrack account"
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
            html_content = render_to_string('email/email_verify.html', {
                'full_name': data['full_name'],
                'verify_link': verify_link,
                'site_name': getattr(settings, 'SITE_NAME', 'SolTrack'),
            })
            text_content = f"Hello {data['full_name']},\n\nPlease verify your email by visiting: {verify_link}\n\nThis link expires in 1 hour."

            email = EmailMultiAlternatives(subject, text_content, from_email, [data['email']])
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)

            # redirect to 'check your inbox' page (you can have a template or message)
            # messages.success(request, "✅ Verification email sent. Please check your inbox (link valid for 1 hour).")
            request.session['sent_email'] = form.cleaned_data['email']
            return redirect('email_sent')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = form_class()

    return render(request, 'registration_user_info.html', {
        'form': form,
        'role': role.capitalize()
    })


# Step 3: Verify token
def verify_email(request, token):
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
        pending_id = payload.get('pending_id')
    except signing.SignatureExpired:
        messages.error(request, "This verification link has expired. Please register again.")
        return redirect('choose_role')
    except signing.BadSignature:
        messages.error(request, "Invalid verification link.")
        return redirect('choose_role')

    pending = get_object_or_404(PendingUser, id=pending_id, email=payload.get('email'))
    # ensure token matches stored value (extra safety)
    if pending.token != token:
        messages.error(request, "Token mismatch or invalid link.")
        return redirect('choose_role')

    pending.is_verified = True
    pending.save()

    # redirect to organization step, pass token in URL
    return redirect('register_organization', token=token)


# Step 4: Organization info & finalize user creation
def register_organization(request, token):
    # validate token again (and ensure verified)
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
        pending_id = payload.get('pending_id')
    except signing.SignatureExpired:
        messages.error(request, "Verification link expired.")
        return redirect('choose_role')
    except signing.BadSignature:
        messages.error(request, "Invalid link.")
        return redirect('choose_role')

    pending = get_object_or_404(PendingUser, id=pending_id, email=payload.get('email'))

    if not pending.is_verified:
        messages.error(request, "Email not verified. Please verify your email first.")
        return redirect('choose_role')

    role = pending.role.lower()
    form_class = BuyerOrgForm if role == 'buyer' else SellerOrgForm

    if request.method == 'POST':
        form = form_class(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data

            # Create actual CustomUser and set hashed password stored in pending.password
            # We'll create the user object and assign the hashed password directly
            user = CustomUser(
                email=pending.email,
                full_name=pending.name,
            )
            # assign hashed password directly (pending.password already hashed with make_password)
            user.password = pending.password
            # other flags
            user.is_active = True
            user.is_approved = False  # admin approval required
            user.role = role.capitalize() if hasattr(user, 'role') else role  # keep same style as your other code

            # org fields
            user.organization = cd.get('organization', '')
            
            # ----- Address Fields -----
            region = cd.get("region")
            province = cd.get("province")
            city = cd.get("city")
            barangay = cd.get("barangay")
            full_address_input = cd.get("full_address")

            # Build full final address
            if full_address_input:
                final_address = f"{full_address_input}, {barangay}, {city}, {province}, {region}, Philippines"
            else:
                final_address = f"{barangay}, {city}, {province}, {region}, Philippines"

            user.address = final_address  # save combined address
            user.m_address = cd.get('m_address', '')

            uploaded_files = request.FILES.getlist('business_license')

            if uploaded_files:
                uploaded_urls = []

                for f in uploaded_files:
                    file_bytes = f.read()

                    timestamp = int(time.time())
                    path = f"business_license/{pending.id}_{timestamp}_{f.name}"

                    response = supabase.storage.from_(settings.SUPABASE_BUCKET).upload(
                        path,
                        file_bytes,
                        file_options={"content-type": f.content_type}
                    )

                    print("UPLOAD RESPONSE:", response.__dict__)  # ⭐ RUN ONCE TO SEE STRUCTURE

                    # universal success check
                    if getattr(response, "error", None) in [None, {}, ""]:
                        public_url = supabase.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)
                        uploaded_urls.append(public_url)
                    else:
                        print("Supabase upload error:", response.error)


                # Save as JSON list of URLs or comma-separated
                user.business_license = ";".join(uploaded_urls)

            # try geocoding address (same as you used earlier)
            address = user.address
            if address:
                try:
                    url = f"https://photon.komoot.io/api/?q={address}"
                    response = requests.get(url, timeout=5).json()
                    if response.get("features"):
                        coords = response["features"][0]["geometry"]["coordinates"]
                        user.longitude = coords[0]
                        user.latitude = coords[1]
                except Exception:
                    # silently ignore geocode errors
                    pass

            user.save()

            # Delete the pending user record
            pending.delete()

            messages.success(request, "🎉 Registration complete! Your account has been created and is pending admin approval.")
            return redirect('login')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = form_class()

    return render(request, 'registration_organization.html', {
        'form': form,
        'role': role.capitalize(),
        'token': token
    })

def email_sent_view(request):
    email = request.session.pop('sent_email', None)
    return render(request, 'registration_email_sent.html', {'email': email})


# Logout view
def logout_view(request):
    logout(request)
    request.session.flush()
    messages.info(request, "👋 You’ve been logged out.")
    return redirect('index')
