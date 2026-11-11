-- Consulta de metadados; não cria recursos.
SELECT schema_name, location
FROM `brasileirao-data-platform.region-us.INFORMATION_SCHEMA.SCHEMATA`
WHERE schema_name IN ('ds_bronze', 'ds_silver', 'ds_gold', 'ds_control')
ORDER BY schema_name;
