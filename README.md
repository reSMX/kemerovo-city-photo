# Интерактивная карта состояния города: анализ фотографий

Локальный анализатор фотографий Кемерово: EXIF и GPS, исправление ориентации,
наблюдения модели через Ollama, оценка видимого состояния от 0 до 10, SQLite и CSV.
Оригиналы не изменяются. Неизвестные значения остаются пустыми.

Веб-карта находится в отдельном репозитории
[kemerovo-photo-map](https://github.com/reSMX/kemerovo-photo-map).
[Переносимый просмотрщик](https://github.com/reSMX/kemerovo-photo-map-portable)
показывает готовые результаты без анализа. Здесь нет веб-сервера.

## Требования и установка

Python 3.11+; скрипты PowerShell рассчитаны на Windows. Для анализа нужна
[Ollama](https://ollama.com/download/windows) с локальными весами
`qwen3-vl:4b-instruct-q4_K_M`. Интернет нужен для установки и загрузки весов;
сам анализ обращается только к localhost. GPU ускоряет обработку.

Все команды выполняются из корня репозитория:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
ollama pull qwen3-vl:4b-instruct-q4_K_M
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 doctor
```

`doctor` показывает окружение и доступность модели. Проверяйте поле `ollama.error`:
диагностика может завершиться с кодом 0 при недоступном сервере.
Веса во время анализа не скачиваются.

Прямые зависимости закреплены в `pyproject.toml`. `requirements-lock.txt` — полный
снимок проверенного окружения Windows/Python 3.14, включая тесты. Для других версий
Python используйте установку из `pyproject.toml`. Поддержка HEIF — extra `heif`.

## Конфигурация

```powershell
Copy-Item .\config.example.yaml .\config.yaml
```

В `config.yaml` задайте `input` — папку с фотографиями. Пути разрешаются относительно
YAML-файла. Локальный `config.yaml` исключён из Git.

| Файл | Назначение |
|---|---|
| `config.example.yaml` | Контекст 8192, ответ до 4096 токенов, CPU-буфер 4 кадра / 2 потока |
| `config.full.yaml` | Текущий пакетный запуск: контекст 16384, ответ до 12288 токенов, буфер 2 кадра / 1 поток |
| `city_photo/resources/assessment.txt` | Промпт |
| `city_photo/resources/rubric.yaml` | Рубрика объектных оценок |
| `city_photo/resources/photo_scoring.yaml` | Формула итогового балла |

Без явных путей используются те же ресурсы внутри пакета. Общий бюджет
`photo_deadline_seconds` по умолчанию 90 секунд, максимум 180. Он включает ожидание
подготовки, ориентацию, анализ и повторы. Сетевой `timeout` действует отдельно.

## Первый запуск и новые фото

Подставьте свою папку вместо `D:\map_photos`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 prepare -InputFolder D:\map_photos -Config config.yaml
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 sample -Config config.yaml
```

Первая команда создаёт реестр; вторая анализирует до 20 ещё не завершённых фото
и сохраняет CSV в `output`. После просмотра результатов:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 all -Config config.yaml
# Добавить новые фото из той же папки и продолжить:
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 update -InputFolder D:\map_photos -Config config.yaml
```

Неизменённые успешные записи используют кэш. Смена модели, промпта, рубрики или
параметров изображения меняет ключ кэша. Изменение только итоговой формулы требует
экспорта, без нового инференса. Ctrl+C сохраняет завершённые записи; повторите `all`
с прежней конфигурацией, чтобы продолжить.

Один workspace привязан к одному входному корню. Для другого архива задайте
`-Workspace work_other -OutputFolder output_other`. Несколько папок в общую базу
сайта добавляет его `import_folders.py`; не меняйте `input_root` вручную.

## Длительный анализ и ошибки

Для уже импортированного реестра, `config.full.yaml`, `work` и `output`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_analysis.ps1
```

Скрипт при необходимости запускает Ollama и продолжает анализ. CPU готовит следующие
кадры параллельно одному запросу модели. Runner блокирует второй такой запуск,
обновляет CSV каждые 10 кадров или 60 секунд, пишет `work/analysis_status.json`
и удерживает Windows от автоматического сна. Остановить после текущего кадра:

```powershell
New-Item -ItemType File -Path .\work\stop.request -Force
```

Остановка по запасу виртуальной памяти отключена в штатном запуске. Включить её:

```powershell
.\.venv\Scripts\python.exe -u run_background.py --config config.full.yaml --workspace work --output output --memory-guard
```

Тайм-аут получает статус `manual_review`, ошибка модели — `model_error`. Повторить
только эти статусы без сохранённого результата с лимитом **180 секунд на фото**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\retry_failed_analysis.ps1
```

Готовые результаты и новые ожидающие кадры этот проход пропускает. Файлы `unreadable`
и `unsupported` требуют отдельного исправления. Планирование повтора и параметры
сервера описаны в [эксплуатации](docs/operations.md).

## Результаты и проверка

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 export -Config config.full.yaml
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 review -Config config.full.yaml
```

`results.csv` содержит все записи, `review.csv` — снимки для проверки,
`run_summary.json` — статусы и скорость. Экспорт создаёт актуальный `data_dictionary.md`.
CSV: UTF-8 BOM, разделитель `;`, пустая ячейка означает null. Для координат в Excel
используйте импорт с десятичной точкой.

Баллы характеризуют видимую часть кадра. Экспериментальная формула не измеряет
благосостояние жителей и не заменяет осмотр на месте.

- [Формула оценки](docs/scoring.md), [поля CSV](docs/csv-fields.md).
- [Ручные правки и разметка](docs/review.md).
- [Локальная география](docs/geography.md).
- [Сравнение моделей](docs/model-comparison.md).
- [Разделение архива между устройствами](docs/distributed.md).
- [Проверки и ограничения](docs/validation.md).

Фото, GPS, ответы модели, базы и результаты остаются локально. Не отправляйте их
в облачные API или GitHub. Сохраняйте `work`: это база, кэш и история правок.
Исходные фотографии должны оставаться доступны по зарегистрированным путям.

## Проверки и сборка

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir dist
.\.venv\Scripts\python.exe -m city_photo --help
.\.venv\Scripts\python.exe run_background.py --help
```

Тесты синтетические, без запуска рабочей модели. Они проверяют код, а не точность
Qwen. Wheel включает пакет и ресурсы. Скрипты запускаются из клона репозитория.
Отдельные линтер, статическая проверка типов и CI не настроены.
Полный список команд доступен через CLI `--help`.

## Структура

```text
city_photo/             анализатор, CLI, SQLite, экспорт и ресурсы
scripts/                сравнение моделей, разделение фото, объединение CSV
tests/                  синтетические проверки
docs/                   эксплуатация, оценка, география и форматы
examples/               демонстрационный CSV, не реальная съёмка
config.*.yaml           примеры и текущая пакетная конфигурация
run.ps1                 импорт, выборка, продолжение, экспорт, ручная проверка
start_analysis.ps1      продолжение пакетного анализа
run_background.py       runner, также используемый соседним веб-проектом
retry_*.ps1             повтор ошибок и его планирование
start_ollama_safe.ps1   запуск локального сервера
```

`.venv`, `work`, `output`, `maps`, `comparison_*`, локальные настройки и материалы
презентации исключены из Git. Это окружение и рабочие данные, а не исходный код.
