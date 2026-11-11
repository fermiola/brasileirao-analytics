SELECT IF(COUNT(*) = 0, 1, 0) AS violations
FROM `brasileirao-data-platform.ds_gold.tb_classificacao`
