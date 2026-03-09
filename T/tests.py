"""
T/tasks.py
──────────
Called by django-crontab every midnight.
CRON line in settings.py:
    CRONJOBS = [('0 0 * * *', 'T.tasks.distribute_daily_income')]

Can also be run manually:
    python manage.py runcrons          (requires django-crontab)
    or just call distribute_daily_income() from a management command
"""
from django.utils import timezone
from datetime import timedelta

from .models import Purchase, Wallet, IncomeDayRecord, Transaction, generate_txn_id


def distribute_daily_income():
    """
    Iterates all active purchases and credits missed daily income
    from their start date up to yesterday (not today—today will
    be handled on next run or on user login via _process_daily_income).
    """
    today = timezone.now().date()

    for purchase in Purchase.objects.filter(is_active=True).select_related('user'):
        start_date = purchase.start_date.date()
        days_paid  = IncomeDayRecord.objects.filter(purchase=purchase).count()

        if days_paid >= purchase.days:
            purchase.is_active = False
            purchase.save()
            continue

        wallet, _ = Wallet.objects.get_or_create(user=purchase.user)
        changed   = False

        current = start_date
        while current < today and days_paid < purchase.days:
            day_key = current.strftime("%Y-%m-%d")
            _, created = IncomeDayRecord.objects.get_or_create(
                purchase=purchase, day_key=day_key
            )
            if created:
                wallet.balance      += purchase.daily_income
                wallet.total_income += purchase.daily_income
                days_paid += 1
                changed = True

                Transaction.objects.create(
                    user     = purchase.user,
                    txn_id   = generate_txn_id("INC"),
                    title    = f"Daily Income - {purchase.plan_name}",
                    amount   = purchase.daily_income,
                    txn_type = "INCOME",
                    status   = "success",
                )
            current += timedelta(days=1)

        if changed:
            wallet.save()
            