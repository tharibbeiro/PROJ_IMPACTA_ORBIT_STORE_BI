"""Cria/recria um banco SQLite com bases raw e analytics originais.
Compativel com Python 3.9+; usa apenas biblioteca padrao.
Uso: python backend/criar_banco_sqlite.py
"""
from pathlib import Path
import csv
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'sql'/'orbit_store.sqlite'
RAW={'campanhas':'Campanhas','categorias':'Categorias','clientes':'Clientes',
     'devolucoes':'Devolucoes','entregas':'Entregas','itens_pedido':'ItensPedido',
     'pagamentos':'Pagamentos','pedidos':'Pedidos','produtos':'Produtos','trafego_diario':'TrafegoDiario'}
INTEGER_FIELDS={
    'quantidade','quantidade_devolvida','qtde_itens','qtde_devolvida','ativo','sessoes','usuarios',
    'visitas_produto','adicoes_carrinho','checkouts','parcelas','pedido_elegivel',
    'prazo_estimado_dias','entrega_concluida','tempo_entrega_dias','entrega_atrasada',
    'ano','mes','trimestre','dia_semana','fim_semana',
    'pedidos_totais','pedidos_validos','pedidos_cancelados','clientes_ativos',
    'unidades_vendidas','unidades_devolvidas','entregas_concluidas','entregas_atrasadas',
    'frequencia_pedidos','recencia_dias','score_r','score_f','score_m'
}

def coluna_tipo(nome):
    if nome.endswith('_id') and nome not in ['data_id']: return 'INTEGER'
    if nome in INTEGER_FIELDS: return 'INTEGER'
    # Todos os valores financeiros sao carregados como REAL no arquivo original.
    if nome.startswith(('receita','custo','valor','cmv','margem','taxa','desconto','investimento','ticket','preco')) or nome in ('roas','percentual','qtde_propostas'):
        return 'REAL'
    return 'TEXT'

def importar_csv(conn,pasta,nome_arquivo,nome_tabela):
    caminho=ROOT/'data'/pasta/(nome_arquivo+'.csv')
    with caminho.open(encoding='utf-8-sig', newline='') as f:
        rd=csv.DictReader(f,delimiter=';')
        cols=rd.fieldnames
        if not cols: raise ValueError(f'Arquivo sem cabecalho: {caminho}')
        tipos=['TEXT' if (pasta=='brutos' and nome_arquivo=='produtos' and c=='ativo') else coluna_tipo(c) for c in cols]
        campos=', '.join('"%s" %s'%(c,t) for c,t in zip(cols,tipos))
        conn.execute(f'CREATE TABLE "{nome_tabela}" ({campos})')
        insert=f'INSERT INTO "{nome_tabela}" VALUES ({",".join("?" for _ in cols)})'
        lote=[];total=0
        for row in rd:
            vals=[]
            for c,t in zip(cols,tipos):
                val=row[c]
                if val=='':val=None
                elif t=='INTEGER': val=int(float(val))
                elif t=='REAL': val=float(val)
                vals.append(val)
            lote.append(vals)
            if len(lote)>=1000:
                conn.executemany(insert,lote);total+=len(lote);lote=[]
        if lote:conn.executemany(insert,lote);total+=len(lote)
    return total

def main():
    DB.parent.mkdir(exist_ok=True)
    if DB.exists():DB.unlink()  # recria o demonstrativo de forma idempotente
    con=sqlite3.connect(DB)
    try:
        for arq,tabela in RAW.items():
            n=importar_csv(con,'brutos',arq,'raw_'+tabela)
            print(f'raw_{tabela:<25} {n:>7} registros')
        for caminho in sorted((ROOT/'data/tratados').glob('*.csv')):
            tabela='analytics_'+caminho.stem
            n=importar_csv(con,'tratados',caminho.stem,tabela)
            print(f'{tabela:<30} {n:>7} registros')
        con.executescript('''
        CREATE INDEX idx_pedidos_data ON analytics_FatoPedidos(data_id);
        CREATE INDEX idx_pedidos_cliente ON analytics_FatoPedidos(cliente_id);
        CREATE INDEX idx_itens_pedido ON analytics_FatoItensPedido(pedido_id);
        CREATE INDEX idx_itens_produto ON analytics_FatoItensPedido(produto_id);
        CREATE INDEX idx_clientes_id ON analytics_DimCliente(cliente_id);
        CREATE INDEX idx_produtos_id ON analytics_DimProduto(produto_id);
        CREATE VIEW vw_ResumoMensal AS
        SELECT ano_mes, pedidos_totais, pedidos_validos, receita_total_liquida,
               margem_contribuicao, ticket_medio, margem_pct
        FROM analytics_IndicadoresMensais;
        CREATE VIEW vw_VendasPorProduto AS
        SELECT p.produto_id, p.nome_produto, p.categoria,
               ROUND(SUM(i.receita_produtos_liquida),2) AS receita_produtos,
               SUM(CASE WHEN i.pedido_elegivel=1 THEN i.quantidade ELSE 0 END) AS unidades_vendidas
        FROM analytics_FatoItensPedido i
        JOIN analytics_DimProduto p ON p.produto_id=i.produto_id
        GROUP BY p.produto_id,p.nome_produto,p.categoria;
        CREATE VIEW vw_VendasPorUF AS
        SELECT c.uf, ROUND(SUM(p.receita_total_liquida),2) AS receita_liquida,
               SUM(p.pedido_elegivel) AS pedidos_validos
        FROM analytics_FatoPedidos p
        JOIN analytics_DimCliente c ON c.cliente_id=p.cliente_id
        GROUP BY c.uf;
        CREATE VIEW vw_FunilCanalMensal AS
        SELECT substr(data_id,1,7) AS ano_mes, canal_venda,
               SUM(sessoes) AS sessoes, SUM(adicoes_carrinho) AS adicoes_carrinho,
               SUM(checkouts) AS checkouts
        FROM analytics_FatoTrafegoDiario
        GROUP BY substr(data_id,1,7),canal_venda;
        ''')
        con.commit()
        print(f'\nOK | SQLite criado: {DB} | {DB.stat().st_size/1024/1024:.2f} MB')
    finally:con.close()

if __name__=='__main__':main()
