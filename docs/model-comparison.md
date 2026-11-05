# Сравнение Instruct и Thinking на 12 фото

Сравнение использует локальные Instruct и Thinking. Команды выполняются из корня
репозитория. Для запуска:

```powershell
.\.venv\Scripts\python.exe -m scripts.compare_models --workspace work --output comparison_12
```

Скрипт фиксирует выборку из 12 разных групп, использует одинаковые оригиналы и общую
проверку ориентации через Instruct. Обеим моделям выделяется контекст 16384 и лимит
ответа 12288, temperature=0.2, seed=42. Thinking включается явно только для Thinking.
Это сравнение результатов при рабочем бюджете, а не при искусственно коротком лимите.
Веса `qwen3-vl:4b` и `qwen3-vl:4b-instruct-q4_K_M` должны быть подготовлены заранее.
Повторный запуск продолжает завершённые записи. `--phase instruct|thinking|report`
позволяет отдельно запускать этапы и пересобрать отчёт без повторного инференса.

В comparison_12: REPORT.md, comparison_summary.json, blind_review.csv с A/B рядом,
human_labels.csv для независимой разметки, model_key.json для раскрытия названий,
shared_orientation.json, timings.csv со временем каждого кадра и отдельные SQLite/CSV/сырые ответы двух моделей.
Ссылки на оригиналы и подготовленные копии — локальные пути в blind_review.csv.
Лучше сначала заполнить human_labels по фото, потом смотреть ответы A/B.

После заполнения одинаковой разметки сравните качество:

```powershell
.\.venv\Scripts\python.exe -m city_photo evaluate --workspace comparison_12/instruct --labels comparison_12/human_labels.csv --output comparison_12/instruct_evaluation.json
.\.venv\Scripts\python.exe -m city_photo evaluate --workspace comparison_12/thinking --labels comparison_12/human_labels.csv --output comparison_12/thinking_evaluation.json
```

Без разметки отчёт показывает согласие категорий, расхождения presence, абсолютную
разницу баллов, несовпадения null и время: среднее, медиану, минимум/максимум,
загрузку модели отдельно и общее время с повторами. Он не утверждает, какая модель правильнее.
Выборка 12 мала: это первичная диагностика, не доказательство качества на всём архиве.
