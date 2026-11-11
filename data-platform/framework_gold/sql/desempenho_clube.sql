-- Gold: desempenho de cada clube como mandante e visitante.
-- Granularidade: temporada + clube + mando.
-- A tabela de destino é recriada atomicamente a cada execução.
WITH partidas_clube AS (
  -- Uma linha para o clube mandante em cada partida finalizada.
  SELECT
    temporada,
    mandante AS clube,
    'Mandante' AS mando,
    gols_mandante AS gols_pro,
    gols_visitante AS gols_contra
  FROM `{source}`
  WHERE status = 'Finalizado'
    AND gols_mandante IS NOT NULL
    AND gols_visitante IS NOT NULL

  UNION ALL

  -- Uma linha para o clube visitante na mesma partida.
  SELECT
    temporada,
    visitante AS clube,
    'Visitante' AS mando,
    gols_visitante AS gols_pro,
    gols_mandante AS gols_contra
  FROM `{source}`
  WHERE status = 'Finalizado'
    AND gols_mandante IS NOT NULL
    AND gols_visitante IS NOT NULL
),
indicadores AS (
  SELECT
    temporada,
    clube,
    mando,
    COUNT(*) AS jogos,
    COUNTIF(gols_pro > gols_contra) AS vitorias,
    COUNTIF(gols_pro = gols_contra) AS empates,
    COUNTIF(gols_pro < gols_contra) AS derrotas,
    SUM(gols_pro) AS gols_pro,
    SUM(gols_contra) AS gols_contra
  FROM partidas_clube
  GROUP BY temporada, clube, mando
)
SELECT
  temporada,
  clube,
  mando,
  jogos,
  vitorias,
  empates,
  derrotas,
  3 * vitorias + empates AS pontos,
  gols_pro,
  gols_contra,
  gols_pro - gols_contra AS saldo_gols,
  ROUND(100 * SAFE_DIVIDE(3 * vitorias + empates, 3 * jogos), 2) AS aproveitamento
FROM indicadores;
