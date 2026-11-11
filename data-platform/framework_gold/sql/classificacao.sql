-- SELECT reutilizavel: a consulta deve retornar o resultado completo da tabela Gold.
-- Marcador {source} e substituido pelo orquestrador por um identificador validado.
-- Apenas partidas finalizadas com placares preenchidos entram na classificacao.
WITH partidas AS (
  SELECT temporada, mandante AS clube,
         gols_mandante AS gols_pro, gols_visitante AS gols_contra
  FROM `{source}`
  WHERE status = 'Finalizado'
    AND gols_mandante IS NOT NULL AND gols_visitante IS NOT NULL
  UNION ALL
  SELECT temporada, visitante AS clube,
         gols_visitante AS gols_pro, gols_mandante AS gols_contra
  FROM `{source}`
  WHERE status = 'Finalizado'
    AND gols_mandante IS NOT NULL AND gols_visitante IS NOT NULL
),
indicadores AS (
  SELECT temporada, clube,
         COUNT(*) AS jogos,
         COUNTIF(gols_pro > gols_contra) AS vitorias,
         COUNTIF(gols_pro = gols_contra) AS empates,
         COUNTIF(gols_pro < gols_contra) AS derrotas,
         SUM(gols_pro) AS gols_pro,
         SUM(gols_contra) AS gols_contra
  FROM partidas
  GROUP BY temporada, clube
),
classificacao AS (
  SELECT temporada, clube, jogos, vitorias, empates, derrotas,
         gols_pro, gols_contra,
         3 * vitorias + empates AS pontos,
         gols_pro - gols_contra AS saldo_gols,
         ROUND(SAFE_DIVIDE(3 * vitorias + empates, 3 * jogos) * 100, 2) AS aproveitamento
  FROM indicadores
)
SELECT
  ROW_NUMBER() OVER (
    PARTITION BY temporada
    ORDER BY pontos DESC, vitorias DESC, saldo_gols DESC, gols_pro DESC, clube ASC
  ) AS posicao,
  temporada, clube, jogos, vitorias, empates, derrotas,
  gols_pro, gols_contra, pontos, saldo_gols, aproveitamento
FROM classificacao
