# Словарь CSV

UTF-8 BOM; разделитель ; по умолчанию. Пустая ячейка = null. Объектные оценки целые 0–10; итоговый photo_score округлён до двух знаков.
Для координат в Excel: Данные → Из текста/CSV → локаль English (United States), десятичная точка.
Текст с началом формулы экранируется апострофом; SQLite хранит исходный текст.

| Поле | Значение |
|---|---|
| filename | Имя оригинала |
| relative_path | Путь от входного корня |
| image_id | Стабильный ID относительного пути |
| territory_type | courtyard/street/boulevard/park_square/private_sector/other/mixed/unknown |
| road_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| sidewalk_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| wall_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| grass_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| curb_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| vegetation_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| playground_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| parking_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| litter_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| road_damage_score | 0–10/null; больше = выраженнее видимая проблема |
| sidewalk_damage_score | 0–10/null; больше = выраженнее видимая проблема |
| wall_damage_score | 0–10/null; больше = выраженнее видимая проблема |
| wall_graffiti_score | 0–10/null; больше = выраженнее видимая проблема |
| grass_damage_score | 0–10/null; больше = выраженнее видимая проблема |
| curb_damage_score | 0–10/null; больше = выраженнее видимая проблема |
| vegetation_abundance_score | 0–10/null; больше = обильнее деревья/кустарники |
| vegetation_damage_score | 0–10/null; больше = выраженнее видимая проблема |
| playground_damage_score | 0–10/null; больше = выраженнее видимая проблема |
| parking_damage_score | 0–10/null; больше = выраженнее видимая проблема |
| litter_score | 0–10/null; больше = выраженнее видимая проблема |
| road_damage_description | Наблюдаемое объяснение или причина ограничения/проверки |
| sidewalk_damage_description | Наблюдаемое объяснение или причина ограничения/проверки |
| wall_damage_description | Наблюдаемое объяснение или причина ограничения/проверки |
| wall_graffiti_description | Наблюдаемое объяснение или причина ограничения/проверки |
| grass_damage_description | Наблюдаемое объяснение или причина ограничения/проверки |
| curb_damage_description | Наблюдаемое объяснение или причина ограничения/проверки |
| vegetation_abundance_description | Наблюдаемое объяснение или причина ограничения/проверки |
| vegetation_damage_description | Наблюдаемое объяснение или причина ограничения/проверки |
| playground_damage_description | Наблюдаемое объяснение или причина ограничения/проверки |
| parking_damage_description | Наблюдаемое объяснение или причина ограничения/проверки |
| litter_description | Наблюдаемое объяснение или причина ограничения/проверки |
| road_description | Наблюдаемое объяснение или причина ограничения/проверки |
| road_presence_status | present/absent/uncertain |
| road_assessability | assessable/partial/not_assessable/not_applicable |
| road_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| sidewalk_description | Наблюдаемое объяснение или причина ограничения/проверки |
| sidewalk_presence_status | present/absent/uncertain |
| sidewalk_assessability | assessable/partial/not_assessable/not_applicable |
| sidewalk_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| wall_description | Наблюдаемое объяснение или причина ограничения/проверки |
| wall_presence_status | present/absent/uncertain |
| wall_assessability | assessable/partial/not_assessable/not_applicable |
| wall_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| grass_description | Наблюдаемое объяснение или причина ограничения/проверки |
| grass_presence_status | present/absent/uncertain |
| grass_assessability | assessable/partial/not_assessable/not_applicable |
| grass_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| curb_description | Наблюдаемое объяснение или причина ограничения/проверки |
| curb_presence_status | present/absent/uncertain |
| curb_assessability | assessable/partial/not_assessable/not_applicable |
| curb_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| vegetation_description | Наблюдаемое объяснение или причина ограничения/проверки |
| vegetation_presence_status | present/absent/uncertain |
| vegetation_assessability | assessable/partial/not_assessable/not_applicable |
| vegetation_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| playground_description | Наблюдаемое объяснение или причина ограничения/проверки |
| playground_presence_status | present/absent/uncertain |
| playground_assessability | assessable/partial/not_assessable/not_applicable |
| playground_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| parking_description | Наблюдаемое объяснение или причина ограничения/проверки |
| parking_presence_status | present/absent/uncertain |
| parking_assessability | assessable/partial/not_assessable/not_applicable |
| parking_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| litter_presence_status | present/absent/uncertain |
| litter_assessability | assessable/partial/not_assessable/not_applicable |
| litter_visibility_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| road_damage_assessment_status | assessable/partial/not_assessable/not_applicable |
| road_damage_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| sidewalk_damage_assessment_status | assessable/partial/not_assessable/not_applicable |
| sidewalk_damage_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| wall_damage_assessment_status | assessable/partial/not_assessable/not_applicable |
| wall_damage_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| wall_graffiti_assessment_status | assessable/partial/not_assessable/not_applicable |
| wall_graffiti_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| grass_damage_assessment_status | assessable/partial/not_assessable/not_applicable |
| grass_damage_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| curb_damage_assessment_status | assessable/partial/not_assessable/not_applicable |
| curb_damage_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| vegetation_abundance_assessment_status | assessable/partial/not_assessable/not_applicable |
| vegetation_abundance_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| vegetation_damage_assessment_status | assessable/partial/not_assessable/not_applicable |
| vegetation_damage_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| playground_damage_assessment_status | assessable/partial/not_assessable/not_applicable |
| playground_damage_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| parking_damage_assessment_status | assessable/partial/not_assessable/not_applicable |
| parking_damage_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| litter_assessment_status | assessable/partial/not_assessable/not_applicable |
| litter_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| latitude | Широта EPSG:4326, десятичные градусы |
| longitude | Долгота EPSG:4326, десятичные градусы |
| gps_status | valid/missing/invalid |
| gps_accuracy_m | Только известная EXIF точность в метрах; иначе null |
| captured_at | ISO 8601, без смещения если оно неизвестно |
| captured_at_raw | Исходная EXIF строка времени |
| timezone_status | unknown/exif_offset/user_assumption |
| metadata_source | Pillow/ExifTool/manual_correction |
| width | Ширина оригинала в пикселях |
| height | Высота оригинала в пикселях |
| exif_orientation | Исходный EXIF 1–8; применяется включая зеркальное отражение |
| clockwise_rotation | Дополнительный поворот по часовой стрелке ПОСЛЕ EXIF: 0/90/180/270 |
| orientation_reason | Наблюдаемое объяснение или причина ограничения/проверки |
| orientation_certain | Самооценка ориентации модели 0/1, не калиброванная вероятность |
| long_side | Фактическое ограничение стороны для инференса |
| context | Фактический контекст в токенах |
| degraded | Снижение разрешения/контекста после ошибки памяти |
| surface_type | paved/unpaved/mixed/unknown |
| mural_present | 1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто |
| mural_status | mural/no_mural/mural_or_graffiti_uncertain |
| geo_status | located/map_unavailable/gps_missing/outside_city/outside_region |
| map_hash | Версия карты и геоправил |
| gps_buffer_m_used | Буфер сопоставления в метрах |
| gps_buffer_source | exif_accuracy/configured_assumption |
| territory_visual | Категория изображённой территории модели |
| territory_geo | Кандидат карты в точке камеры |
| territory_source | visual/unknown/visual_geo_agree_camera_context_only |
| territory_description | Наблюдаемое объяснение или причина ограничения/проверки |
| courtyard_candidate_id | Кандидаты по карте, не координата объекта |
| courtyard_id | Только подтверждённый вручную ID; GPS — положение камеры |
| courtyard_assignment_status | candidate/confirmed/unknown; подтверждение отдельным ручным решением |
| playground_courtyard_link_status | candidate/confirmed/unknown; подтверждение отдельным ручным решением |
| parking_courtyard_link_status | candidate/confirmed/unknown; подтверждение отдельным ручным решением |
| processing_status | pending/processed/processed_with_review/unreadable/unsupported/model_error |
| needs_review | 0/1, требуется проверка |
| review_reasons | Наблюдаемое объяснение или причина ограничения/проверки |
| error | Ошибка чтения или модели, без base64 |
| exact_duplicate_of | ID первого точного дубликата |
| near_duplicate_group_id | Кандидаты dHash, оценки не копируются |
| schema_version | Версия схемы |
| rubric_version | Версия рабочей рубрики |
| rubric_hash | SHA-256 версии соответствующего входа/модели |
| prompt_version | Версия промпта |
| prompt_hash | SHA-256 версии соответствующего входа/модели |
| config_hash | SHA-256 версии соответствующего входа/модели |
| model_name | Явный локальный тег |
| model_digest | SHA-256 версии соответствующего входа/модели |
| ollama_version | Версия локального сервера |
| processed_at | UTC ISO 8601 |
| photo_score | Экспериментальный балл видимого состояния 0–10, больше лучше; не индекс двора/города |
| photo_score_status | available/provisional/insufficient_data; ни один статус не доказывает точность |
| photo_score_coverage | 0–1 доля взвешенной оценимой информации среди видимых/неуверенных объектов |
| photo_score_lower_bound | Нижняя граница при худшем состоянии всей неоценённой части; не статистический доверительный интервал |
| photo_score_upper_bound | Верхняя граница при лучшем состоянии всей неоценённой части; не статистический доверительный интервал |
| photo_score_metric_count | Число показателей с оценкой, вошедших в сумму |
| photo_score_reason | Ограничение или причина отсутствия итогового балла |
| photo_scoring_version | Версия формулы итогового балла |
| photo_scoring_hash | SHA-256 правил итогового балла |
