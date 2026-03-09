from django.urls import path
from . import views
from .views import purchased_products
urlpatterns = [
    # ── Auth ──
    path('',          views.login_view,  name="login"),
    
    path('register/', views.register,    name="register"),
    path('logout/',   views.user_logout, name="logout"),

    # ── Main pages ──
    path('dashboard/',  views.dashboard,   name="dashboard"),
    path('income/',     views.income_page, name="income"),
    path('my/',         views.my_profile,  name="my_profile"),
    path('team/',       views.team_page,   name="team"),
    path('share/',      views.share_page,  name="share"),
    path('about/',      views.about_page,  name="about"),
    path('messages/',   views.my_message,  name="my_message"),

    # ── Recharge ──
    path('recharge/',         views.recharge_page,   name="recharge"),
    path('payment/',          views.payment_page,    name="payment"),
    path('payment/submit/',   views.submit_payment,  name="submit_payment"),
    path('recharge/records/', views.recharge_records,name="recharge_records"),

    # ── Withdraw ──
    path('withdraw/',            views.withdraw_page,      name="withdraw"),
    path('withdraw/records/',    views.withdrawal_records, name="withdrawal_records"),

    # ── Personal info ──
    path('personal-info/',          views.personal_info,  name="personal_info"),
    path('bind-bank/',              views.bind_bank,      name="bind_bank"),
    path('bind-email/',             views.bind_email,     name="bind_email"),
    path('change-password/',        views.change_password,name="change_password"),

    # ── User API ──
    path('api/wallet/', views.wallet_api,  name="wallet_api"),
    path('api/buy/',    views.buy_product, name="buy_product"),

    # ── Admin panel ──
    path('admin-panel/', views.admin_panel, name="admin_panel"),

    # ── Admin APIs ──
    path('api/admin/user-wallet/<int:user_id>/', views.admin_user_wallet,      name="admin_user_wallet"),
    path('api/admin/wallet-adjust/',             views.admin_wallet_adjust,    name="admin_wallet_adjust"),
    path('api/admin/vip-toggle/',                views.admin_vip_toggle,       name="admin_vip_toggle"),
    path('api/admin/recharge-action/',           views.admin_recharge_action,  name="admin_recharge_action"),
    path('api/admin/withdrawal-action/',         views.admin_withdrawal_action,name="admin_withdrawal_action"),
    path('api/admin/product-toggle/',            views.admin_product_toggle,   name="admin_product_toggle"),
    # NEW VIP ACTIVATE FOR ALL USERS
    path('api/admin/activate-vip-all/', views.activate_vip_all, name="activate_vip_all"),
    path('purchased/', views.purchased_products, name="purchased_products"),
    
]