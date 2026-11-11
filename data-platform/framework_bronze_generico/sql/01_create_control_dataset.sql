CREATE SCHEMA IF NOT EXISTS
  `brasileirao-data-platform.ds_bronze`

OPTIONS (
  location = 'US',
  description = 'Camada Bronze - armazenamento dos dados brutos do Brasileirão'
);