# Карта и конкретные дворы

Команды выполняются из корня репозитория.

Анализ работает без карты: `geo_status=map_unavailable`. Скачивание карты во время
анализа запрещено. Поддерживается импорт готового GeoJSON; автоматического
экспорта OSM нет. Никакие координаты отдельных фото не используются в сетевых запросах.

Получение настоящей карты вручную: в https://overpass-turbo.eu выполните следующий
запрос по административной территории всего города, затем Export → GeoJSON. Проверьте
название и границу отношения в https://www.openstreetmap.org перед использованием.
Результат и дата выгрузки должны храниться локально. При таймауте сервиса повторите
загрузку позднее; не заменяйте границу приблизительным прямоугольником.

```text
[out:json][timeout:180];
rel["boundary"="administrative"]["name"="Кемерово"];
map_to_area->.city;
(
  rel["boundary"="administrative"]["name"="Кемерово"];
  way(area.city)["building"];
  way(area.city)["highway"];
  nwr(area.city)["leisure"~"^(park|garden)$"];
  way(area.city)["highway"="pedestrian"];
);
out geom;
```

GeoJSON должен быть FeatureCollection EPSG:4326, координаты `[долгота, широта]`.
Добавьте свойство `layer`: `boundary` для проверенной границы города, `building`,
`road`, `park`, `pedestrian`. Допустимы Polygon/MultiPolygon, линии дорог.
Неправильная/пустая геометрия отклоняется. Голый экспорт без layer сохраняется,
но не даёт территориальных кандидатов: подготовьте свойства в QGIS.

```powershell
.\.venv\Scripts\python.exe -m city_photo prepare-map --import-file C:\Maps\kemerovo.geojson --output maps/kemerovo.geojson --source https://www.openstreetmap.org --license ODbL-1.0 --attribution "© OpenStreetMap contributors"
# В config.yaml: map_path: maps/kemerovo.geojson
.\.venv\Scripts\python.exe -m city_photo geolocate --workspace work --config config.yaml
```

Сохраняются источник, атрибуция, лицензия, SHA-256 и время импорта в соседнем
`.provenance.json`. Время импорта не выдаётся за время съёмки/актуальность OSM.
Метрические расчёты — EPSG:32645 (UTM 45N), не градусы; подходит Кемерово.
Буфер 30 м при неизвестной точности — допущение. Координаты вне города/у границ
отмечаются; визуальная классификация сохраняется при конфликте с картой.
GPS — точка камеры, кандидат карты не доказывает содержание кадра.

Полигоны дворов: создайте отдельный GeoJSON в QGIS с `courtyard_id`, `layer=courtyard`,
`verification=verified|proposed`, источник проверки. Укажите `courtyards_path`.
Все автоматические связи остаются candidate, даже внутри полигона. После ручной
проверки задайте courtyard_id и courtyard_assignment_status=confirmed через corrections.
Соседство домов, landuse=residential и service-проезд не доказывают двор.
Площадка/парковка не получает вымышленную координату; хранится только статус связи.
