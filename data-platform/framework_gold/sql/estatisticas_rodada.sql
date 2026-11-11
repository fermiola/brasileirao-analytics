-- Query de transformacao: o orquestrador envolve este SELECT em CREATE OR REPLACE TABLE.
-- Uma linha por temporada, rodada e clube que efetivamente jogou.
WITH jogos AS (
  SELECT temporada, rodada, data, mandante AS clube, visitante AS adversario,
    'Mandante' AS mando, gols_mandante AS gols_pro, gols_visitante AS gols_contra
  FROM `{source}`
  WHERE status = 'Finalizado' AND gols_mandante IS NOT NULL AND gols_visitante IS NOT NULL
  UNION ALL
  SELECT temporada, rodada, data, visitante AS clube, mandante AS adversario,
    'Visitante' AS mando, gols_visitante AS gols_pro, gols_mandante AS gols_contra
  FROM `{source}`
  WHERE status = 'Finalizado' AND gols_mandante IS NOT NULL AND gols_visitante IS NOT NULL
),
resultados AS (
 SELECT *, CASE WHEN gols_pro > gols_contra THEN 'Vitoria'
                WHEN gols_pro = gols_contra THEN 'Empate' ELSE 'Derrota' END AS resultado,
   IF(gols_pro > gols_contra, 3, IF(gols_pro = gols_contra, 1, 0)) AS pontos_rodada,
   IF(gols_pro > gols_contra, 1, 0) AS vitoria,
   IF(gols_pro = gols_contra, 1, 0) AS empate,
   IF(gols_pro < gols_contra, 1, 0) AS derrota
 FROM jogos
),
acumulado AS (
 SELECT *,
   COUNT(*) OVER w AS jogos_acumulados,
   SUM(vitoria) OVER w AS vitorias_acumuladas,
   SUM(empate) OVER w AS empates_acumulados,
   SUM(derrota) OVER w AS derrotas_acumuladas,
   SUM(pontos_rodada) OVER w AS pontos_acumulados,
   SUM(gols_pro) OVER w AS gols_pro_acumulados,
   SUM(gols_contra) OVER w AS gols_contra_acumulados
 FROM resultados
 WINDOW w AS (PARTITION BY temporada, clube ORDER BY rodada
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
-- Cada rodada e avaliada com a classificacao dos clubes que ja jogaram ate ela.
-- Assim, clubes sem jogo na rodada continuam participando da classificacao da rodada.
rodadas AS (SELECT DISTINCT temporada, rodada FROM resultados),
clubes AS (SELECT DISTINCT temporada, clube FROM resultados),
classificacao_por_rodada AS (
 SELECT r.temporada, r.rodada, c.clube,
   a.pontos_acumulados, a.vitorias_acumuladas,
   a.gols_pro_acumulados - a.gols_contra_acumulados AS saldo_acumulado,
   a.gols_pro_acumulados
 FROM rodadas r
 JOIN clubes c ON c.temporada = r.temporada
 LEFT JOIN acumulado a
   ON a.temporada = r.temporada
  AND a.clube = c.clube
  AND a.rodada <= r.rodada
 QUALIFY ROW_NUMBER() OVER (
   PARTITION BY r.temporada, r.rodada, c.clube
   ORDER BY a.rodada DESC
 ) = 1
),
posicoes AS (
 SELECT temporada, rodada, clube,
   ROW_NUMBER() OVER (
     PARTITION BY temporada, rodada
     ORDER BY COALESCE(pontos_acumulados, 0) DESC,
              COALESCE(vitorias_acumuladas, 0) DESC,
              COALESCE(saldo_acumulado, 0) DESC,
              COALESCE(gols_pro_acumulados, 0) DESC,
              clube ASC
   ) AS posicao_apos_rodada
 FROM classificacao_por_rodada
)
SELECT a.temporada, a.rodada, a.data, a.clube, a.adversario, a.mando,
 a.gols_pro, a.gols_contra, a.resultado, a.pontos_rodada,
 a.jogos_acumulados, a.vitorias_acumuladas, a.empates_acumulados,
 a.derrotas_acumuladas, a.pontos_acumulados, a.gols_pro_acumulados,
 a.gols_contra_acumulados,
 a.gols_pro_acumulados - a.gols_contra_acumulados AS saldo_gols_acumulado,
 ROUND(SAFE_DIVIDE(a.pontos_acumulados, a.jogos_acumulados * 3) * 100, 2)
   AS aproveitamento_acumulado,
 p.posicao_apos_rodada
FROM acumulado a
JOIN posicoes p USING (temporada, rodada, clube)
