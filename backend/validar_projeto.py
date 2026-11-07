"""Testes de integridade SQLite, sem bibliotecas externas."""
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'sql/orbit_store.sqlite'

def validar():
    if not DB.exists(): raise AssertionError('Banco ausente: executar script 01')
    con=sqlite3.connect(DB)
    checks={
        'raw_Clientes':1200,'raw_Produtos':64,'raw_Pedidos':9000,
        'raw_ItensPedido':16908,'analytics_FatoPedidos':9000,
        'analytics_FatoItensPedido':16908,'analytics_IndicadoresMensais':34,
        'analytics_DimCliente':1200,'analytics_DimProduto':64
    }
    for tabela, esperado in checks.items():
        n=con.execute(f'SELECT COUNT(*) FROM {tabela}').fetchone()[0]
        assert n==esperado,f'{tabela}: {n} x esperado {esperado}'
        print(f'OK {tabela:<34} {n:>6}')
    p=con.execute('''SELECT ROUND(SUM(receita_total_liquida),2),
                            ROUND(SUM(margem_contribuicao),2), SUM(pedido_elegivel)
                       FROM analytics_FatoPedidos''').fetchone()
    m=con.execute('''SELECT ROUND(SUM(receita_total_liquida),2),
                            ROUND(SUM(margem_contribuicao),2), SUM(pedidos_validos)
                       FROM analytics_IndicadoresMensais''').fetchone()
    assert p == m,f'Valores pedidos vs meses divergentes: {p} x {m}'
    assert abs(p[0]-6273952.55)<0.01 and abs(p[1]-2200130.29)<0.01 and p[2]==8331,p
    it=con.execute('SELECT ROUND(SUM(receita_produtos_liquida),2) FROM analytics_FatoItensPedido').fetchone()[0]
    ip=con.execute('SELECT ROUND(SUM(receita_produtos_liquida),2) FROM analytics_FatoPedidos').fetchone()[0]
    assert abs(it-ip)<0.01, f'Itens vs pedidos divergem: {it} x {ip}'
    sem_prod=con.execute('''SELECT COUNT(*) FROM analytics_FatoItensPedido i
                            LEFT JOIN analytics_DimProduto p ON p.produto_id=i.produto_id
                            WHERE p.produto_id IS NULL''').fetchone()[0]
    assert sem_prod==0,'Itens com produtos inexistentes'
    assert (ROOT/'index.html').exists(),'Falta gerar HTML (script 02)'
    c=con.execute('SELECT COUNT(*) FROM analytics_ClientesRFM WHERE frequencia_pedidos>=2').fetchone()[0]
    print(f'OK Receita: R$ {p[0]:,.2f}; Margem: R$ {p[1]:,.2f}; Pedidos validos: {p[2]}')
    print(f'OK Clientes recorrentes: {c}; Integridade de produtos: OK; Dashboard HTML: OK')
    print('TODAS AS VALIDACOES CONCLUIDAS COM SUCESSO!')
    con.close()

if __name__=='__main__':validar()
