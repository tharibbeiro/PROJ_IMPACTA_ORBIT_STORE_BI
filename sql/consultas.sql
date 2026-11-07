-- SQLite: consultas para demonstrar no trabalho (DB Browser for SQLite ou Python)
-- Tabelas foram nomeadas com prefixos raw_ e analytics_, pois SQLite nao tem schemas SQL Server.

-- 1. Volumes principais
SELECT 'Clientes' AS tabela, COUNT(*) AS registros FROM raw_Clientes
UNION ALL SELECT 'Produtos', COUNT(*) FROM raw_Produtos
UNION ALL SELECT 'Pedidos', COUNT(*) FROM raw_Pedidos
UNION ALL SELECT 'Itens', COUNT(*) FROM raw_ItensPedido
UNION ALL SELECT 'FatoPedidos', COUNT(*) FROM analytics_FatoPedidos
UNION ALL SELECT 'FatoItensPedido', COUNT(*) FROM analytics_FatoItensPedido
UNION ALL SELECT 'Meses', COUNT(*) FROM analytics_IndicadoresMensais;

-- 2. Conciliacao financeira (resultado: duas linhas iguais)
SELECT 'FatoPedidos' AS origem, ROUND(SUM(receita_total_liquida),2) AS receita,
 ROUND(SUM(margem_contribuicao),2) AS margem FROM analytics_FatoPedidos
UNION ALL
SELECT 'IndicadoresMensais', ROUND(SUM(receita_total_liquida),2),
 ROUND(SUM(margem_contribuicao),2) FROM analytics_IndicadoresMensais;

-- 3. Ranking de categorias
SELECT p.categoria, ROUND(SUM(i.receita_produtos_liquida),2) receita
FROM analytics_FatoItensPedido i
JOIN analytics_DimProduto p ON p.produto_id = i.produto_id
GROUP BY p.categoria ORDER BY receita DESC;

-- 4. 10 produtos com maior faturamento
SELECT nome_produto, categoria, receita_produtos
FROM vw_VendasPorProduto ORDER BY receita_produtos DESC LIMIT 10;

-- 5. Status dos pedidos
SELECT status_pedido, COUNT(*) pedidos FROM analytics_FatoPedidos
GROUP BY status_pedido ORDER BY pedidos DESC;
