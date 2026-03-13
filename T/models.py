import random
import string
import time
from django.db import models
from django.contrib.auth.models import User


# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def generate_unique_code():
    characters = string.ascii_letters + string.digits
    while True:
        code = ''.join(random.choices(characters, k=6))
        if not Profile.objects.filter(referral_code=code).exists():
            return code


def generate_txn_id(prefix="TXN"):
    return f"{prefix}-{int(time.time() * 1000)}-{random.randint(0, 999)}"


# ─────────────────────────────────────────
#  PROFILE
# ─────────────────────────────────────────
class Profile(models.Model):
    user            = models.OneToOneField(User, on_delete=models.CASCADE)
    mobile          = models.CharField(max_length=10, unique=True)
    invitation_code = models.CharField(max_length=20, blank=True)
    referral_code   = models.CharField(max_length=6,  unique=True, blank=True)
    is_vip          = models.BooleanField(default=False)
    # bank details (replaces bind-bank localStorage)
    bank_name       = models.CharField(max_length=100, blank=True)
    bank_ifsc       = models.CharField(max_length=20,  blank=True)
    bank_account    = models.CharField(max_length=20,  blank=True)
    # email / nickname (replaces bind-email localStorage)
    email           = models.EmailField(blank=True)
    nickname        = models.CharField(max_length=50, blank=True)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = generate_unique_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} ({self.mobile})"


# ─────────────────────────────────────────
#  WALLET
# ─────────────────────────────────────────
class Wallet(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE)
    recharge     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.user.username} — ₹{self.balance}"


# ─────────────────────────────────────────
#  PURCHASE
# ─────────────────────────────────────────
class Purchase(models.Model):
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchases')
    txn_id       = models.CharField(max_length=60, unique=True)
    plan_name    = models.CharField(max_length=100)
    price        = models.DecimalField(max_digits=12, decimal_places=2)
    daily_income = models.DecimalField(max_digits=12, decimal_places=2)
    days         = models.IntegerField()
    start_date   = models.DateTimeField(auto_now_add=True)
    is_active    = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} — {self.plan_name}"


# ─────────────────────────────────────────
#  DAILY INCOME DAY RECORD
# ─────────────────────────────────────────
class IncomeDayRecord(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='income_days')
    day_key  = models.CharField(max_length=12)   # YYYY-MM-DD
    income   = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ('purchase', 'day_key')

    def __str__(self):
        return f"{self.purchase.plan_name} - {self.day_key} - ₹{self.income}" 
    
# ─────────────────────────────────────────
#  TRANSACTION LOG
# ─────────────────────────────────────────
class Transaction(models.Model):
    TYPE_CHOICES = [
        ('RECHARGE', 'Recharge'),
        ('PURCHASE', 'Purchase'),
        ('INCOME',   'Daily Income'),
        ('REFUND',   'Refund'),
        ('WITHDRAW', 'Withdrawal'),
        ('VIP',      'VIP Status'),
    ]
    STATUS_CHOICES = [
        ('success',  'Success'),
        ('pending',  'Pending'),
        ('rejected', 'Rejected'),
    ]
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    txn_id   = models.CharField(max_length=60, unique=True)
    title    = models.CharField(max_length=200)
    amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    txn_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    date     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.user.username} — {self.txn_id}"


# ─────────────────────────────────────────
#  RECHARGE REQUEST  (replaces payment.js / pending recharge localStorage)
# ─────────────────────────────────────────
class RechargeRequest(models.Model):
    STATUS = [('pending','Pending'),('approved','Approved'),('rejected','Rejected')]
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recharge_requests')
    txn_id       = models.CharField(max_length=60, unique=True)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)
    utr          = models.CharField(max_length=50, blank=True)
    screenshot   = models.ImageField(upload_to='recharge_screenshots/', blank=True, null=True)
    status       = models.CharField(max_length=20, choices=STATUS, default='pending')
    created_at   = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} — ₹{self.amount} ({self.status})"


# ─────────────────────────────────────────
#  WITHDRAW REQUEST  (replaces withdraw.js localStorage)
# ─────────────────────────────────────────
class WithdrawRequest(models.Model):
    STATUS = [('pending','Pending'),('success','Success'),('rejected','Rejected')]
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdraw_requests')
    txn_id       = models.CharField(max_length=60, unique=True)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)
    charge       = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    final_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status       = models.CharField(max_length=20, choices=STATUS, default='Processing')
    created_at   = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} — ₹{self.amount} ({self.status})"


# ─────────────────────────────────────────
#  PRODUCT STATUS  (replaces productStatus localStorage)
# ─────────────────────────────────────────
class ProductStatus(models.Model):
    product_key  = models.CharField(max_length=50, unique=True)
    product_name = models.CharField(max_length=100)
    is_active    = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Product Statuses"

    def __str__(self):
        return f"{self.product_name} ({'ON' if self.is_active else 'OFF'})"
    

