SELECT COUNT(*) AS violations
FROM `brasileirao-data-platform.ds_silver.tb_partidas`
WHERE (status = 'Finalizado' AND (gols_mandante IS NULL OR gols_visitante IS NULL))
   OR (gols_mandante < 0 OR gols_visitante < 0)
