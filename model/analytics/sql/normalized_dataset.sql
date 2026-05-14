-- Источник истины для аналитики: нормализованные данные после apps.normalization.service.normalize_raw_listing.
-- Запрос показывает базовую связку normalized_listings -> listings -> valuations.

select
  nl.id as normalized_id,
  nl.raw_listing_id,
  nl.listing_id,
  nl.normalized_payload,
  nl.validation_status,
  nl.validation_errors,
  nl.validation_warnings,
  nl.is_train_eligible,
  l.city,
  l.district,
  l.area,
  l.kitchen_area_m2,
  l.rooms,
  l.floor,
  l.total_floors,
  l.year_built,
  l.latitude,
  l.longitude,
  l.listing_price,
  l.listing_currency,
  v.predicted_price,
  v.undervaluation_delta,
  v.undervaluation_percent,
  v.score
from normalized_listings nl
left join listings l on l.id = nl.listing_id
left join valuations v on v.listing_id = l.id
where nl.validation_status = 'accepted'
order by nl.id asc;

