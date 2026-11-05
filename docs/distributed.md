# Два устройства

Дополнительный сценарий; обычный запуск на одном компьютере описан в README.
Команды выполняются из корня клона после установки `.[test]`.
Фото и манифесты передаются отдельно от GitHub.

## Разделение

```powershell
.\.venv\Scripts\python.exe -m scripts.split_photos --input D:\map_photos --output D:\map_photos_split
.\.venv\Scripts\python.exe -m scripts.split_photos --input D:\map_photos_split\part_2 --verify-manifest D:\map_photos_split\part_2_manifest.json
```

Создаются две группы копий с проверкой SHA-256, оригиналы не меняются. При нечётном
числе первая группа больше на один файл. Манифесты лежат рядом с входными папками,
не внутри: импорт регистрирует все файлы. Повтор разделения проверяет прежний набор
и существующие копии.

На обоих устройствах установите Python, зависимости и одинаковые веса Ollama.
Не переносите `.venv`. Согласуйте commit, digest модели, ресурсы и параметры.
Для каждой группы выделите отдельные workspace и папку экспорта.

## Анализ своей группы

```powershell
Copy-Item .\config.example.yaml .\config.part2.yaml
# В config.part2.yaml: input: D:/map_photos_split/part_2
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 prepare -InputFolder D:\map_photos_split\part_2 -Workspace work_part2 -OutputFolder output_part2 -Config config.part2.yaml
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 sample -Workspace work_part2 -OutputFolder output_part2 -Config config.part2.yaml
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 all -Workspace work_part2 -OutputFolder output_part2 -Config config.part2.yaml
```

Для первой группы замените `part2`/`part_2` на `part1`/`part_1`. После прерывания повторите
`all`. Для новых файлов используйте `update` с прежними путями. Не применяйте `--force`
для обычного продолжения.

## Объединение CSV

Передайте `results.csv` каждой группы в отдельной папке на одно устройство:

```powershell
.\.venv\Scripts\python.exe -m scripts.merge_results --inputs output_part1/results.csv output_part2/results.csv --output merged/results.csv
```

Скрипт сохраняет ошибки и отклоняет пересекающиеся ID/пути, разные схемы CSV
или версии модели, промпта, рубрики и формулы. `--allow-mixed` используйте только
для намеренно смешанного экспорта. Проверьте число строк по манифестам.
Сохраните commit, digest, параметры, время и сведения о ручной проверке.
