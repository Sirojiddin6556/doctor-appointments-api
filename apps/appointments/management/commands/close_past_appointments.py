"""Перевод завершённых по времени записей в статус `completed`.

Жизненный цикл записи: `booked` создаётся при бронировании, `cancelled` —
при отмене пациентом, `completed` — когда время приёма прошло. Отдельного
endpoint'а для завершения нет: приём считается состоявшимся по факту
`end_time < now`, если его не отменили. Команда рассчитана на запуск по
расписанию (cron / periodic task), например раз в 10 минут.
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.appointments.models import Appointment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Пометить прошедшие booked-записи как completed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать число записей к обновлению, но не менять данные.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        due = Appointment.objects.filter(status=Appointment.Status.BOOKED, end_time__lt=now)
        count = due.count()

        if options["dry_run"]:
            self.stdout.write(f"К переводу в completed: {count} записей (dry-run, изменений нет).")
            return

        updated = due.update(status=Appointment.Status.COMPLETED)
        logger.info("Переведено записей в статус completed: %s", updated)
        self.stdout.write(self.style.SUCCESS(f"Переведено в completed: {updated} записей."))
