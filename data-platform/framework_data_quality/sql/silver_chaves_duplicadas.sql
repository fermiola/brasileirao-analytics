SELECT COUNT(*) AS violations FROM (
  SELECT temporada, rodada, mandante, visitante
  FROM `brasileirao-data-platform.ds_silver.tb_partidas`
  GROUP BY 1, 2, 3, 4 HAVING COUNT(*) > 1
)
