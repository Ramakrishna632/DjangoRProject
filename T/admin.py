from django.contrib import admin
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils.html import format_html
import uuid
from .models import (
    Profile,
    Wallet,
    Purchase,
    IncomeDayRecord,
    Transaction,
    RechargeRequest,
    WithdrawRequest,
    ProductStatus
)


# ─────────────────────────────────────────
# PROFILE
# ─────────────────────────────────────────
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "mobile",
        "referral_code",
        "is_vip",
        "bank_name",
        "bank_ifsc"
    )
    list_editable = ("is_vip",)

    search_fields = (
        "user__username",
        "mobile",
        "referral_code"
    )

    list_filter = ("is_vip",)
    # ADD THIS
    fields = (
        "user",
        "mobile",
        "referral_code",
        "is_vip",
        "bank_name",
        "bank_ifsc",
        "bank_account"
    )

# ─────────────────────────────────────────
# WALLET
# ─────────────────────────────────────────
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "balance",
        "recharge",
        "total_income"
    )

    search_fields = ("user__username",)

    list_editable = (
        "balance",
        "recharge",
        "total_income"
    )


# ─────────────────────────────────────────
# PURCHASE
# ─────────────────────────────────────────
@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "plan_name",
        "price",
        "daily_income",
        "days",
        "start_date",
        "is_active"
    )

    list_filter = (
        "is_active",
        "plan_name"
    )

    search_fields = (
        "user__username",
        "txn_id"
    )


# ─────────────────────────────────────────
# DAILY INCOME RECORD
# ─────────────────────────────────────────
@admin.register(IncomeDayRecord)
class IncomeDayRecordAdmin(admin.ModelAdmin):

    list_display = (
        "purchase",
        "day_key"
    )


# ─────────────────────────────────────────
# TRANSACTIONS
# ─────────────────────────────────────────
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "txn_id",
        "title",
        "amount",
        "txn_type",
        "status",
        "date"
    )

    list_filter = (
        "txn_type",
        "status"
    )

    search_fields = (
        "user__username",
        "txn_id"
    )

    ordering = ("-date",)


# ─────────────────────────────────────────
# RECHARGE REQUEST
# ─────────────────────────────────────────
from django.utils.html import format_html

@admin.register(RechargeRequest)
class RechargeRequestAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "amount",
        "utr",
        "status_colored",
        "screenshot_preview",
        "created_at"
    )

    list_filter = ("status",)

    search_fields = (
        "user__username",
        "utr",
        "txn_id"
    )

    actions = ["approve_recharge", "reject_recharge"]

    # Screenshot preview
    def screenshot_preview(self, obj):
        if obj.screenshot:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="height:100px;border-radius:6px;" />'
                '</a>',
                obj.screenshot.url
            )
        return "No Image"

    screenshot_preview.short_description = "Screenshot"

    # Colored status
    def status_colored(self, obj):

        if obj.status == "approved":
            color = "green"

        elif obj.status == "rejected":
            color = "red"

        else:
            color = "orange"

        return format_html(
            '<b style="color:{}">{}</b>',
            color,
            obj.status.upper()
        )

    status_colored.short_description = "Status"

    # Approve recharge
    def approve_recharge(self, request, queryset):

        for obj in queryset:

            if obj.status == "pending":

                wallet, created = Wallet.objects.get_or_create(user=obj.user)

                # wallet.balance += obj.amount
                wallet.recharge += obj.amount
                wallet.save()

                Transaction.objects.create(
                    user=obj.user,
                    txn_id="TXN" + str(uuid.uuid4().hex[:8]).upper(),
                    title="Recharge Approved",
                    amount=obj.amount,
                    txn_type="credit",
                    status="success",
                    date=timezone.now()
                )

                obj.status = "approved"
                obj.processed_at = timezone.now()
                obj.save()

    approve_recharge.short_description = "Approve Recharge"

    # Reject recharge
    def reject_recharge(self, request, queryset):

        queryset.update(status="rejected")

    reject_recharge.short_description = "Reject Recharge"


# ─────────────────────────────────────────
# WITHDRAW REQUEST
# ─────────────────────────────────────────
@admin.register(WithdrawRequest)
class WithdrawRequestAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "amount",
        "final_amount",
        "charge",
        "status",
        "created_at"
    )

    list_filter = ("status",)

    search_fields = (
        "user__username",
        "txn_id"
    )

    actions = ["approve_withdraw", "reject_withdraw"]

    # APPROVE
    def approve_withdraw(self, request, queryset):

        for obj in queryset:

            if obj.status == "pending":

                wallet = Wallet.objects.get(user=obj.user)
                # wallet, created = Wallet.objects.get_or_create(user=obj.user)
                if wallet.balance >= obj.amount:

                    wallet.balance -= obj.amount
                    wallet.save()

                    obj.status = "success"
                    obj.processed_at = timezone.now()
                    obj.save()

                    Transaction.objects.filter(
                        user=obj.user,
                        txn_id=obj.txn_id
                    ).update(status="success")

    approve_withdraw.short_description = "Approve Withdraw"

    # REJECT
    def reject_withdraw(self, request, queryset):

        for obj in queryset:

            if obj.status == "pending":

                obj.status = "rejected"
                obj.processed_at = timezone.now()
                obj.save()

                Transaction.objects.filter(
                    user=obj.user,
                    txn_id=obj.txn_id
                ).update(status="rejected")

    reject_withdraw.short_description = "Reject Withdraw"

# ─────────────────────────────────────────
# PRODUCT STATUS
# ─────────────────────────────────────────
@admin.register(ProductStatus)
class ProductStatusAdmin(admin.ModelAdmin):

    list_display = (
        "product_name",
        "product_key",
        "is_active"
    )

    list_editable = ("is_active",)

