# Brasileirão Data Platform — pacote revisado

Este pacote contém os frameworks Python comentados de **Bronze, Silver, Gold, Data Quality e Orquestrador Geral**, além de arquivos JSON, SQL e documentação de execução.

**Fonte incluída:** `framework_bronze_generico/Brasileirao_Dados.xlsx`. Verifique se sua publicação é autorizada antes de enviá-la ao GitHub.

**Orquestrador oficial:** `Orquestrador_Geral/orquestrador_pipeline.py`. O arquivo homônimo em `framework_data_quality/` foi preservado como legado, não como ponto de entrada principal.

**Primeiro passo:** leia `README.md` na raiz para configurar o ambiente, criar datasets/procedure, validar localmente e executar `--all`.

**Limite da revisão:** códigos de processamento foram preservados; os arquivos Python foram verificados por compilação sintática e os JSONs por parsing. A revisão do ZIP não executou jobs no GCP.
