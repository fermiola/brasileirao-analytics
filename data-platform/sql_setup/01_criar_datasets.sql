-- Executar no BigQuery Studio, região US, antes do pipeline.
-- Troque o projeto se usar outro ambiente.
CREATE SCHEMA IF NOT EXISTS `brasileirao-data-platform.ds_bronze` OPTIONS(location='US', description='Camada Bronze - dados brutos');
CREATE SCHEMA IF NOT EXISTS `brasileirao-data-platform.ds_silver` OPTIONS(location='US', description='Camada Silver - dados tratados');
CREATE SCHEMA IF NOT EXISTS `brasileirao-data-platform.ds_gold` OPTIONS(location='US', description='Camada Gold - indicadores');
CREATE SCHEMA IF NOT EXISTS `brasileirao-data-platform.ds_control` OPTIONS(location='US', description='Auditoria e controle');
