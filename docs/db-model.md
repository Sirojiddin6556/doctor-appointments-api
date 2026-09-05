# Модель БД — детальная спецификация

Каждое поле и constraint ниже привязаны к конкретному бизнес-правилу из ТЗ (пункты 1–8), чтобы на созвоне можно было объяснить не только "что", но и "зачем".

## User (расширяет Django AbstractUser)

| Поле | Тип | Ограничения |
|---|---|---|
| id | BigAutoField | PK |
| username | CharField(150) | unique (из AbstractUser) |
| email | EmailField | — |
| password | CharField | хеш через Django `set_password` (PBKDF2), сами не пишем |
| role | CharField(10) | choices: `patient`/`doctor`/`admin`, default `patient`, `db_index=True` |

Решение: роль — отдельное явное поле, а не перегрузка `is_staff`. `is_staff`/`is_superuser` остаются только для доступа в Django admin, бизнес-права идут через `role`.

## Doctor

| Поле | Тип | Ограничения |
|---|---|---|
| id | BigAutoField | PK |
| user | OneToOneField(User) | `unique=True`, `on_delete=CASCADE`, `related_name="doctor_profile"` |
| specialization | CharField(100) | `db_index=True` (нужен для фильтра `GET /api/doctors/?specialization=`) |
| branch | CharField(100) | `db_index=True` (нужен для фильтра `?branch=`) |

## Slot

| Поле | Тип | Ограничения |
|---|---|---|
| id | BigAutoField | PK |
| doctor | ForeignKey(Doctor) | `on_delete=CASCADE`, `related_name="slots"` |
| start_time | DateTimeField | `USE_TZ=True`, хранится в UTC |
| end_time | DateTimeField | UTC |
| created_at | DateTimeField | `auto_now_add=True` |

**Constraints:**
- `CheckConstraint(end_time > start_time)` — целостность интервала.
- `ExcludeConstraint` (PostgreSQL GIST, расширение `btree_gist`) на `(doctor_id WITH =, tsrange(start_time, end_time) WITH &&)` → **правило 7**: врач физически не может создать два пересекающихся слота, гонка запросов тоже исключена, т.к. проверка на уровне БД, а не только в Python.
- Индекс `(doctor_id, start_time)` — для быстрой выборки `GET /api/slots/mine/` и `GET /api/doctors/{id}/slots/?date=`.

## Appointment

| Поле | Тип | Ограничения |
|---|---|---|
| id | BigAutoField | PK |
| slot | ForeignKey(Slot) | `on_delete=PROTECT`, `related_name="appointments"` (не `OneToOne`, т.к. один слот может иметь несколько записей за свою историю: booked → cancelled → снова booked) |
| patient | ForeignKey(User) | `on_delete=PROTECT`, `related_name="appointments"` |
| start_time | DateTimeField | **денормализовано** из `slot.start_time` в момент бронирования |
| end_time | DateTimeField | денормализовано из `slot.end_time` |
| status | CharField(10) | choices: `booked`/`cancelled`/`completed`, `db_index=True` |
| created_at | DateTimeField | `auto_now_add=True` |
| cancelled_at | DateTimeField | `null=True, blank=True` |

Зачем денормализация времени: без неё нельзя построить `ExcludeConstraint` для правила 3 (constraint не может «прыгать» через join на `Slot`). Время копируется один раз при создании записи и после этого не меняется — это безопасно, т.к. отменённая запись не переиспользуется (создаётся новая при повторном бронировании).

**Constraints:**
- `UniqueConstraint(fields=["slot"], condition=Q(status="booked"), name="unique_active_booking_per_slot")` → **правило 1**: на уровне БД в любой момент времени может существовать максимум одна `booked`-запись на слот, независимо от того, сколько `cancelled` записей накопилось. Комбинируется с `select_for_update()` внутри `transaction.atomic()` в view, чтобы конфликт возвращался как понятный `400/409`, а не как необработанное исключение (`IntegrityError` ловится явно).
- `ExcludeConstraint` (GIST) на `(patient_id WITH =, tsrange(start_time, end_time) WITH &&)` **WHERE status='booked'** → **правило 3**: у пациента не может быть двух пересекающихся по времени активных записей — гарантия на уровне БД, а не только проверка в сериализаторе.
- `CheckConstraint(end_time > start_time)`.
- Индекс `(patient_id, status)` — для `GET /api/appointments/` (только свои).
- Индекс `(status, start_time)` — для отчётов админа с фильтром по диапазону дат.

## Сводная таблица: правило → механизм защиты

| # | Правило | Механизм |
|---|---|---|
| 1 | Слот не бронируется дважды | `select_for_update()` + `UniqueConstraint` (partial) на БД |
| 2 | Нельзя бронировать прошедший слот | Валидация в сериализаторе: `slot.start_time > timezone.now()` |
| 3 | Нет пересекающихся `booked` у пациента | `ExcludeConstraint` (GIST) на Appointment + проверка в сериализаторе |
| 4 | Отмена только за >2 часа | Валидация в `cancel()`: `slot.start_time - now() > timedelta(hours=2)` |
| 5 | Отменённый слот снова свободен | «Свободен» = нет активной `booked`-записи на слот (вычисляется, не хранится как флаг) |
| 6 | Доступ только к своим объектам | `get_queryset()` фильтрует по `request.user` + object-level permission |
| 7 | Врач не создаёт пересекающиеся слоты себе | `ExcludeConstraint` (GIST) на Slot |
| 8 | UTC хранение, ISO 8601 на входе | `USE_TZ=True`, `TIME_ZONE="UTC"`, DRF `DateTimeField` (ISO 8601 из коробки) |

Ключевое архитектурное решение: где возможно, бизнес-правило дублируется на двух уровнях — валидация в API (даёт понятный `400` с текстом ошибки) **и** constraint в БД (даёт гарантию даже если в коде где-то ошибка или два процесса API работают параллельно). Для проверяющих это как раз то, о чём сказано в ТЗ: "ma'lumotlar butunligi" — целостность данных должна держаться на уровне БД, а не только на доверии к коду приложения.
