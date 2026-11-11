-- Transformacao SELECT para o orquestrador Gold REPLACE_ATOMIC.
-- Uma linha por temporada e clube; ate cinco partidas finalizadas mais recentes.
WITH jogos_ordenados AS (
  SELECT
    temporada, clube, rodada, data, adversario, mando,
    gols_pro, gols_contra, resultado, pontos_rodada,
    ROW_NUMBER() OVER (
      PARTITION BY temporada, clube
      ORDER BY rodada DESC, data DESC, adversario ASC
    ) AS ordem_recencia
  FROM `{source}`
  WHERE resultado IN ('Vitoria', 'Empate', 'Derrota')
),
ultimos_cinco AS (
  SELECT * FROM jogos_ordenados WHERE ordem_recencia <= 5
),
indicadores AS (
  SELECT
    temporada,
    clube,
    COUNT(*) AS jogos,
    COUNTIF(resultado = 'Vitoria') AS vitorias,
    COUNTIF(resultado = 'Empate') AS empates,
    COUNTIF(resultado = 'Derrota') AS derrotas,
    SUM(pontos_rodada) AS pontos,
    SUM(gols_pro) AS gols_pro,
    SUM(gols_contra) AS gols_contra,
    MAX(rodada) AS ultima_rodada_disputada,
    STRING_AGG(
      CASE resultado
        WHEN 'Vitoria' THEN 'V'
        WHEN 'Empate' THEN 'E'
        ELSE 'D'
      END,
      '-' ORDER BY ordem_recencia DESC
    ) AS sequencia_resultados
  FROM ultimos_cinco
  GROUP BY temporada, clube
)
SELECT
  temporada, clube, jogos, vitorias, empates, derrotas, pontos,
  gols_pro, gols_contra,
  gols_pro - gols_contra AS saldo_gols,
  ROUND(SAFE_DIVIDE(pontos, jogos * 3) * 100, 2) AS aproveitamento,
  ultima_rodada_disputada,
  sequencia_resultados
FROM indicadores
