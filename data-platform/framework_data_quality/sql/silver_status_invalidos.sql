SELECT COUNT(*) AS violations
FROM `brasileirao-data-platform.ds_silver.tb_partidas`
WHERE status IS NULL OR status NOT IN ('Finalizado', 'Agendado')
