from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as auth_login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction as db_transaction
from datetime import date, timedelta
from decimal import Decimal
import json, re

from .models import (
    Profile, Wallet, Purchase, IncomeDayRecord,
    Transaction, RechargeRequest, WithdrawRequest,
    ProductStatus, generate_txn_id
)

# ══════════════════════════════════════════════
#  PLAN DATA  (single source of truth)
# ══════════════════════════════════════════════
PLAN_DATA = {
    "starter":   {"name": "Plan Starter",    "price": 580,    "daily": 40,   "days": 16,  "vip": False},
    "growth":    {"name": "Plan Growth",     "price": 2199,   "daily": 100,  "days": 30,  "vip": False},
    "lucky":     {"name": "Lucky",           "price": 5999,   "daily": 250,  "days": 30,  "vip": False},
    "master8":   {"name": "Plan Master 8",   "price": 14111,  "daily": 466,  "days": 45,  "vip": False},
    "fortune11": {"name": "Plan Fortune 11", "price": 31000,  "daily": 775,  "days": 40,  "vip": False},
    "elite27":   {"name": "Plan Elite 27",   "price": 75999,  "daily": 2000, "days": 100, "vip": False},
    "vision108": {"name": "Plan Vision 108", "price": 108999, "daily": 4000, "days": 75,  "vip": False},
   
    "plan1": {"name": "Starter Solar Pack",   "price": 1000,   "daily": 350,  "days": 30, "vip": True},
    "plan2": {"name": "Smart Energy Kit",     "price": 3200,   "daily": 1200, "days": 30, "vip": True},
    "plan3": {"name": "Power Generator Set",  "price": 5000,   "daily": 1800, "days": 30, "vip": True},
    "plan4": {"name": "Energy Booster Unit",  "price": 8000,   "daily": 2800, "days": 30, "vip": True},
    "plan5": {"name": "Advanced Power Pack",  "price": 12000,  "daily": 4200, "days": 30, "vip": True},
    "plan6": {"name": "Industrial Energy Kit","price": 20000,  "daily": 7000, "days": 30, "vip": True},
    "plan7": {"name": "Mega Power Station",   "price": 35000,  "daily": 12000,"days": 30, "vip": True},
    "plan8": {"name": "Ultra Energy System",  "price": 50000,  "daily": 17000,"days": 30, "vip": True},
    "plan9": {"name": "Ultimate Power Plant", "price": 100000, "daily": 35000,"days": 30, "vip": True},
}

RECHARGE_AMOUNTS = [580, 1850, 4550, 8950, 12500, 21000]

def is_admin(user):
    return user.is_staff or user.is_superuser


# ══════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════
def register(request):
    if request.method == "POST":
        name            = request.POST.get("name", "").strip()
        mobile          = request.POST.get("mobile", "").strip()
        password        = request.POST.get("password", "")
        invitation_code = request.POST.get("invitation_code", "")

        if not re.match(r'^\d{10}$', mobile):
            return render(request, "register.html", {"error": "Mobile must be exactly 10 digits"})
        if User.objects.filter(username=mobile).exists():
            return render(request, "register.html", {"error": "Mobile already registered"})

        user = User.objects.create_user(username=mobile, password=password, first_name=name)

        Profile.objects.create(
            user=user,
            mobile=mobile,
            invitation_code=invitation_code
        )

        # 👇 Give ₹30 welcome bonus
        Wallet.objects.create(
            user=user,
            balance=30
        )

        # 👇 Optional: store transaction record
        Transaction.objects.create(
            user=user,
            txn_id=generate_txn_id("BONUS"),
            title="Welcome Bonus ₹30",
            amount=30,
            txn_type="BONUS"
        )

        _seed_product_status()

        return redirect("login")

    return render(request, "register.html")

# def login_view(request):
#     if request.user.is_authenticated:
#         return redirect("admin_panel" if request.user.is_staff else "dashboard")

#     if request.method == "POST":
#         mobile   = request.POST.get("mobile", "").strip()
#         password = request.POST.get("password", "")
#         user     = authenticate(request, username=mobile, password=password)
#         if user:
#             auth_login(request, user)
#             # Ensure Wallet exists for every user on login
#             Wallet.objects.get_or_create(user=user)
#             # Ensure Profile exists safely
#             Profile.objects.get_or_create(
#                 user=user,
#                 defaults={"mobile": user.username[:10]}
#             )
#             if user.is_staff or user.is_superuser:
#                 return redirect("admin_panel")
#             return redirect("dashboard")
#         return render(request, "login.html", {"error": "Invalid mobile number or password"})
#     return render(request, "login.html")


from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login

def login_view(request):

    if request.method == "POST":
        mobile = request.POST.get("mobile")
        password = request.POST.get("password")

        user = authenticate(request, username=mobile, password=password)

        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            return render(request, "login.html", {"error": "Invalid login"})

    return render(request, "login.html")

def user_logout(request):
    logout(request)
    return redirect("login")


# ══════════════════════════════════════════════
#  DASHBOARD  (index page)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def dashboard(request):
    try:
        _process_daily_income(request.user)
    except Exception:
        pass  # Never let income engine crash the dashboard

    wallet,  _ = Wallet.objects.get_or_create(user=request.user)
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={"mobile": request.user.username[:10]}
    )
    return render(request, "dashboard.html", {
        "wallet":           wallet,
        "profile":          profile,
        "is_vip":           profile.is_vip,
        "product_statuses": _get_product_statuses(),
    })


# ══════════════════════════════════════════════
#  DAILY INCOME ENGINE
# ══════════════════════════════════════════════
def _process_daily_income(user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    today = date.today()

    for purchase in Purchase.objects.filter(user=user, is_active=True):
        start     = purchase.start_date.date()
        days_paid = IncomeDayRecord.objects.filter(purchase=purchase).count()

        if days_paid >= purchase.days:
            purchase.is_active = False
            purchase.save()
            continue

        current = start
        while current < today and days_paid < purchase.days:
            day_key = current.strftime("%Y-%m-%d")
            _, created = IncomeDayRecord.objects.get_or_create(purchase=purchase, day_key=day_key)
            if created:
                wallet.balance      += purchase.daily_income
                wallet.total_income += purchase.daily_income
                days_paid += 1
                Transaction.objects.create(
                    user=user, txn_id=generate_txn_id("INC"),
                    title=f"Daily Income - {purchase.plan_name}",
                    amount=purchase.daily_income, txn_type='INCOME'
                )
            current += timedelta(days=1)

    wallet.save()


# ══════════════════════════════════════════════
#  BUY PRODUCT  (AJAX POST)
# ══════════════════════════════════════════════
@login_required(login_url='login')
@require_POST
def buy_product(request):
    data        = json.loads(request.body)
    product_key = data.get("product_key")
    plan        = PLAN_DATA.get(product_key)
    if not plan:
        return JsonResponse({"success": False, "message": "Invalid product"})

    user    = request.user
    wallet, _  = Wallet.objects.get_or_create(user=user)
    profile, _ = Profile.objects.get_or_create(user=user)

    ps = ProductStatus.objects.filter(product_key=product_key).first()
    if ps and not ps.is_active:
        return JsonResponse({"success": False, "message": "This product is currently unavailable"})

    if plan["vip"] and not profile.is_vip:
        return JsonResponse({"success": False, "message": "VIP will br sctivated soon."})

    price           = Decimal(str(plan["price"]))
    total_available = wallet.recharge + wallet.balance
    if total_available < price:
        return JsonResponse({"success": False, "message": "Insufficient funds"})

    with db_transaction.atomic():
        remaining = price
        if wallet.recharge >= remaining:
            wallet.recharge -= remaining
            remaining = Decimal('0')
        else:
            remaining      -= wallet.recharge
            wallet.recharge = Decimal('0')
            wallet.balance -= remaining

        if plan["vip"]:
            profile.is_vip = True
            profile.save()

        txn_id = generate_txn_id("BUY")
        Purchase.objects.create(
            user=user, txn_id=txn_id, plan_name=plan["name"],
            price=price, daily_income=plan["daily"], days=plan["days"]
        )
        Transaction.objects.create(
            user=user, txn_id=txn_id,
            title=f"Purchased - {plan['name']}",
            amount=price, txn_type='PURCHASE'
        )
        wallet.save()

    return JsonResponse({
        "success": True,
        "message": f"{plan['name']} purchased successfully!",
        "wallet": _wallet_json(wallet, profile),
    })


# ══════════════════════════════════════════════
#  RECHARGE PAGE  (replaces recharge.html + recharge.js)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def recharge_page(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    return render(request, "recharge.html", {
        "wallet": wallet,
        "amounts": RECHARGE_AMOUNTS,
    })


# ══════════════════════════════════════════════
#  PAYMENT PAGE  (replaces payment.html + payment.js)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def payment_page(request):
    amount = request.GET.get("amount", 580)
    return render(request, "payment.html", {"amount": amount})


@login_required(login_url='login')
@require_POST
def submit_payment(request):
    """User submits UTR + optional screenshot after paying."""
    amount     = Decimal(request.POST.get("amount", "0"))
    utr        = request.POST.get("utr", "").strip()
    screenshot = request.FILES.get("screenshot")

    if not re.match(r'^\d{12}$', utr):
        return render(request, "payment.html", {
            "amount": amount, "error": "UTR must be exactly 12 digits"
        })

    rr = RechargeRequest.objects.create(
        user       = request.user,
        txn_id     = generate_txn_id("RECH"),
        amount     = amount,
        utr        = utr,
        screenshot = screenshot,
        status     = 'pending',
    )
    Transaction.objects.create(
        user=request.user, txn_id=rr.txn_id,
        title=f"Recharge Pending ₹{amount}", amount=amount,
        txn_type='RECHARGE', status='pending'
    )
    return redirect("recharge_records")


# ══════════════════════════════════════════════
#  INCOME HISTORY  (replaces income.html + income.js)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def income_page(request):
    _process_daily_income(request.user)
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    return render(request, "income.html", {
        "wallet": wallet,
        "transactions": transactions,
    })


# ══════════════════════════════════════════════
#  RECHARGE RECORDS  (replaces recharge-record.html)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def recharge_records(request):
    records = RechargeRequest.objects.filter(user=request.user).order_by('-created_at')
    return render(request, "recharge_records.html", {"records": records})


# ══════════════════════════════════════════════
#  WITHDRAWAL  (replaces withdraw.html + withdraw.js)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def withdraw_page(request):
    wallet,  _ = Wallet.objects.get_or_create(user=request.user)
    profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        amount   = Decimal(request.POST.get("amount", "0"))
        password = request.POST.get("password", "")

        if not request.user.check_password(password):
            return render(request, "withdraw.html", {
                "wallet": wallet, "profile": profile,
                "error": "Incorrect password"
            })
        if amount < 99:
            return render(request, "withdraw.html", {
                "wallet": wallet, "profile": profile,
                "error": "Minimum withdrawal is ₹99"
            })
        if wallet.balance < amount:
            return render(request, "withdraw.html", {
                "wallet": wallet, "profile": profile,
                "error": "Insufficient balance"
            })
        if not profile.bank_account or not profile.bank_ifsc:
            return render(request, "withdraw.html", {
                "wallet": wallet, "profile": profile,
                "error": "Please bind your bank account first"
            })

        wr = WithdrawRequest.objects.create(
            user=request.user, txn_id=generate_txn_id("WD"),
            amount=amount, charge=10, final_amount=amount - 10,
        )
        Transaction.objects.create(
            user=request.user, txn_id=wr.txn_id,
            title=f"Withdrawal Request ₹{amount}", amount=amount,
            txn_type='WITHDRAW', status='Processing'
        )
        return redirect("withdrawal_records")

    return render(request, "withdraw.html", {"wallet": wallet, "profile": profile})


# ══════════════════════════════════════════════
#  WITHDRAWAL RECORDS
# ══════════════════════════════════════════════
@login_required(login_url='login')
def withdrawal_records(request):
    records = WithdrawRequest.objects.filter(user=request.user).order_by('-created_at')
    return render(request, "withdrawal_records.html", {"records": records})


# ══════════════════════════════════════════════
#  MY PROFILE  (replaces my.html + my.js)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def my_profile(request):
    wallet,  _ = Wallet.objects.get_or_create(user=request.user)
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return render(request, "my.html", {"wallet": wallet, "profile": profile})


# ══════════════════════════════════════════════
#  PERSONAL INFO  (replaces personal-info + bind pages)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def personal_info(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return render(request, "personal_info.html", {"profile": profile})


@login_required(login_url='login')
def bind_bank(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        ifsc = request.POST.get("ifsc", "").strip().upper()
        acc  = request.POST.get("acc", "").strip()
        if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', ifsc):
            return render(request, "bind_bank.html", {"profile": profile, "error": "Invalid IFSC"})
        if not re.match(r'^\d{9,18}$', acc):
            return render(request, "bind_bank.html", {"profile": profile, "error": "Invalid account number"})
        profile.bank_name    = name
        profile.bank_ifsc    = ifsc
        profile.bank_account = acc
        profile.save()
        return redirect("personal_info")
    return render(request, "bind_bank.html", {"profile": profile})


@login_required(login_url='login')
def bind_email(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        profile.email    = request.POST.get("email", "")
        profile.nickname = request.POST.get("nickname", "")
        profile.save()
        return redirect("personal_info")
    return render(request, "bind_email.html", {"profile": profile})


@login_required(login_url='login')
def change_password(request):
    if request.method == "POST":
        old = request.POST.get("old_password", "")
        new = request.POST.get("new_password", "")
        con = request.POST.get("confirm_password", "")
        if not request.user.check_password(old):
            return render(request, "change_password.html", {"error": "Incorrect old password"})
        if new != con:
            return render(request, "change_password.html", {"error": "Passwords do not match"})
        request.user.set_password(new)
        request.user.save()
        return redirect("login")
    return render(request, "change_password.html")


# ══════════════════════════════════════════════
#  SHARE PAGE  (replaces share.html)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def share_page(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return render(request, "share.html", {"profile": profile})


# ══════════════════════════════════════════════
#  TEAM PAGE  (replaces team.html)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def team_page(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    # Find users who used this user's referral code as invitation
    level1 = Profile.objects.filter(invitation_code=profile.referral_code).select_related('user', 'user__wallet')
    return render(request, "team.html", {"profile": profile, "level1": level1})


# ══════════════════════════════════════════════
#  ABOUT / MESSAGE PAGES
# ══════════════════════════════════════════════
@login_required(login_url='login')
def about_page(request):
    return render(request, "about.html")


@login_required(login_url='login')
def my_message(request):
    return render(request, "my_msg.html")


# ══════════════════════════════════════════════
#  WALLET API  (used by dashboard JS)
# ══════════════════════════════════════════════
@login_required(login_url='login')
def wallet_api(request):
    wallet,  _ = Wallet.objects.get_or_create(user=request.user)
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return JsonResponse(_wallet_json(wallet, profile))


# ══════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def admin_panel(request):
    users               = User.objects.filter(is_staff=False).select_related('wallet', 'profile')
    pending_recharges   = RechargeRequest.objects.filter(status='pending').select_related('user').order_by('-created_at')
    pending_withdrawals = WithdrawRequest.objects.filter(status='pending').select_related('user').order_by('-created_at')
    products            = list(ProductStatus.objects.all().values('pk','product_key','product_name','is_active'))
    return render(request, "admin_panel.html", {
        "users":               users,
        "pending_recharges":   pending_recharges,
        "pending_withdrawals": pending_withdrawals,
        "products":            products,
    })


@login_required(login_url='login')
@user_passes_test(is_admin)
def admin_user_wallet(request, user_id):
    user    = get_object_or_404(User, pk=user_id)
    wallet, _  = Wallet.objects.get_or_create(user=user)
    profile, _ = Profile.objects.get_or_create(user=user)
    return JsonResponse({
        **_wallet_json(wallet, profile),
        "name":   user.first_name,
        "mobile": user.username,
    })


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_POST
def admin_wallet_adjust(request):
    data   = json.loads(request.body)
    uid    = data.get("user_id")
    field  = data.get("field")
    action = data.get("action")
    amount = Decimal(str(data.get("amount", 0)))

    if amount <= 0 or field not in ("balance", "recharge", "total_income"):
        return JsonResponse({"success": False, "message": "Invalid input"})

    user   = get_object_or_404(User, pk=uid)
    wallet, _ = Wallet.objects.get_or_create(user=user)
    current   = getattr(wallet, field)

    setattr(wallet, field, current + amount if action == "add" else max(Decimal('0'), current - amount))
    wallet.save()

    if field == "recharge" and action == "add":
        Transaction.objects.create(
            user=user, txn_id=generate_txn_id("RECH"),
            title=f"Admin Recharge ₹{amount}", amount=amount,
            txn_type='RECHARGE'
        )
    profile, _ = Profile.objects.get_or_create(user=user)
    return JsonResponse({"success": True, "message": f"Done", "wallet": _wallet_json(wallet, profile)})


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_POST
def admin_vip_toggle(request):
    data    = json.loads(request.body)
    user    = get_object_or_404(User, pk=data.get("user_id"))
    approve = bool(data.get("approve"))
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.is_vip = approve
    profile.save()
    label = "VIP Approved" if approve else "VIP Cancelled"
    Transaction.objects.create(
        user=user, txn_id=generate_txn_id("VIP"),
        title=label, amount=0, txn_type='VIP'
    )
    return JsonResponse({"success": True, "message": label, "is_vip": approve})


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_POST
def admin_recharge_action(request):
    data   = json.loads(request.body)
    rr     = get_object_or_404(RechargeRequest, pk=data.get("id"), status='pending')
    action = data.get("action")

    if action == "approve":
        wallet, _ = Wallet.objects.get_or_create(user=rr.user)
        wallet.recharge += rr.amount
        wallet.save()
        rr.status = 'approved'
        rr.processed_at = timezone.now()
        rr.save()
        Transaction.objects.filter(user=rr.user, txn_id=rr.txn_id).update(status='success')
        return JsonResponse({"success": True, "message": f"₹{rr.amount} approved"})
    elif action == "reject":
        rr.status = 'rejected'
        rr.processed_at = timezone.now()
        rr.save()
        Transaction.objects.filter(user=rr.user, txn_id=rr.txn_id).update(status='rejected')
        return JsonResponse({"success": True, "message": "Rejected"})
    return JsonResponse({"success": False, "message": "Invalid action"})


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_POST
def admin_withdrawal_action(request):
    data   = json.loads(request.body)
    wr     = get_object_or_404(WithdrawRequest, pk=data.get("id"), status='pending')
    action = data.get("action")

    if action == "approve":
        wallet, _ = Wallet.objects.get_or_create(user=wr.user)
        if wallet.balance < wr.amount:
            return JsonResponse({"success": False, "message": "User has insufficient balance"})
        wallet.balance -= wr.amount
        wallet.save()
        wr.status = 'success'
        wr.processed_at = timezone.now()
        wr.save()
        Transaction.objects.filter(user=wr.user, txn_id=wr.txn_id).update(status='success')
        return JsonResponse({"success": True, "message": f"₹{wr.final_amount} sent (₹10 charge)"})
    elif action == "reject":
        wr.status = 'rejected'
        wr.processed_at = timezone.now()
        wr.save()
        Transaction.objects.filter(user=wr.user, txn_id=wr.txn_id).update(status='rejected')
        return JsonResponse({"success": True, "message": "Rejected"})
    return JsonResponse({"success": False, "message": "Invalid action"})


@login_required(login_url='login')
@user_passes_test(is_admin)
@require_POST
def admin_product_toggle(request):
    data        = json.loads(request.body)
    product_key = data.get("product_key")
    is_active   = bool(data.get("is_active"))
    plan        = PLAN_DATA.get(product_key)
    if not plan:
        return JsonResponse({"success": False, "message": "Invalid product"})
    ps, _ = ProductStatus.objects.get_or_create(
        product_key=product_key,
        defaults={"product_name": plan["name"], "is_active": True}
    )
    ps.is_active = is_active
    ps.save()
    return JsonResponse({"success": True, "message": f"{plan['name']} {'activated' if is_active else 'disabled'}"})


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
def _seed_product_status():
    for key, plan in PLAN_DATA.items():
        ProductStatus.objects.get_or_create(
            product_key=key,
            defaults={"product_name": plan["name"], "is_active": True}
        )


def _get_product_statuses():
    _seed_product_status()
    return {ps.product_key: ps.is_active for ps in ProductStatus.objects.all()}


def _wallet_json(wallet, profile):
    return {
        "balance":      float(wallet.balance),
        "recharge":     float(wallet.recharge),
        "total_income": float(wallet.total_income),
        "is_vip":       profile.is_vip,
    }


# ── FIX 2: personal_info view — pass info_rows context ──
# Replace your current personal_info view with this:

@login_required(login_url='login')
def personal_info(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    info_rows = [
        ("Name",    request.user.first_name or "—"),
        ("Mobile",  profile.mobile),
        ("Email",   profile.email or "Not set"),
        ("Nickname",profile.nickname or "Not set"),
        ("Bank",    profile.bank_name or "Not linked"),
        ("IFSC",    profile.bank_ifsc or "—"),
        ("Account", profile.bank_account or "—"),
        ("VIP",     "✅ Active" if profile.is_vip else "❌ Not active"),
        ("Referral",profile.referral_code),
    ]
    return render(request, "personal_info.html", {"profile": profile, "info_rows": info_rows})

@login_required(login_url='login')
@user_passes_test(is_admin)
@require_POST
def activate_vip_all(request):
    Profile.objects.update(is_vip=True)
    return JsonResponse({"success": True, "message": "VIP activated for all users"})


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from .models import Profile

def is_admin(user):
    return user.is_staff or user.is_superuser

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Purchase

@login_required(login_url='login')
def purchased_products(request):
    purchases = Purchase.objects.filter(user=request.user).order_by("-start_date")
    return render(request, "purchased.html", {"purchases": purchases})

