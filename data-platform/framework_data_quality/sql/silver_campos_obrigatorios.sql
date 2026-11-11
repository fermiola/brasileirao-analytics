SELECT COUNT(*) AS violations
FROM `brasileirao-data-platform.ds_silver.tb_partidas`
WHERE temporada IS NULL OR rodada IS NULL
   OR mandante IS NULL OR TRIM(mandante) = ''
   OR visitante IS NULL OR TRIM(visitante) = ''
   OR mandante = visitante
