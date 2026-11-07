"""Exporta um HTML offline auto-contido a partir de SQLite (sem pip).
Uso: python backend/gerar_dashboard.py
"""
from pathlib import Path
import sqlite3
import json
ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'sql/orbit_store.sqlite'
TPL=ROOT/'dashboard/modelo_dashboard.html'
SAIDA=ROOT/'index.html'
def centavos(v):
    return int(round((v or 0)*100))

def main():
    if not DB.exists(): raise RuntimeError('Execute primeiro backend/criar_banco_sqlite.py')
    con=sqlite3.connect(DB)
    try:
        pedidos=con.execute('''
        SELECT pedido_id,cliente_id,substr(data_id,1,7),status_pedido,canal_venda,
               pedido_elegivel,receita_total_liquida,margem_contribuicao,receita_produtos_liquida
        FROM analytics_FatoPedidos ORDER BY pedido_id''').fetchall()
        itens=con.execute('''
        SELECT pedido_id,produto_id,receita_produtos_liquida,
               CASE WHEN pedido_elegivel=1 THEN quantidade ELSE 0 END
        FROM analytics_FatoItensPedido ORDER BY item_id''').fetchall()
        pro=con.execute('SELECT produto_id,nome_produto,categoria FROM analytics_DimProduto').fetchall()
        cli=con.execute('SELECT cliente_id,nome,uf FROM analytics_DimCliente').fetchall()
    finally:con.close()
    dados={
        'o':[[int(a),int(b),c,d,e,int(f),centavos(g),centavos(h),centavos(j)] for a,b,c,d,e,f,g,h,j in pedidos],
        'i':[[int(a),int(b),centavos(c),int(d or 0)] for a,b,c,d in itens],
        'p':{str(id):[name,cat] for id,name,cat in pro},
        'c':{str(id):[name,uf] for id,name,uf in cli}
    }
    texto=TPL.read_text(encoding='utf-8')
    obj=json.dumps(dados,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    texto=texto.replace('__DATA_JSON__',obj)
    SAIDA.write_text(texto,encoding='utf-8')
    print(f'Dashboard gerado: {SAIDA} ({SAIDA.stat().st_size/1024/1024:.2f} MB)')
    print(f'Dados integrados: {len(dados["o"])} pedidos; {len(dados["i"])} itens; {len(dados["c"])} clientes; {len(dados["p"])} produtos')

if __name__=='__main__':main()
