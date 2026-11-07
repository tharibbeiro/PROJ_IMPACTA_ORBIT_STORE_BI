"""Transforma os CSVs de entrada em 11 tabelas analíticas usando Pandas/NumPy.
Executar: python backend/processar_metricas.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
MAPEAMENTO={x:None for x in ('campanhas','categorias','clientes','devolucoes','entregas','itens_pedido','pagamentos','pedidos','produtos','trafego_diario')}

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'tratados'


def capturar_offline():
    return {chave:pd.read_csv(ROOT/'data'/'brutos'/f'{chave}.csv',sep=';',encoding='utf-8-sig')
            for chave in MAPEAMENTO}



def normalize_text(s):
    return s.astype('string').str.strip().str.casefold()


def sanitize_money(df,cols):
    for col in cols:
        df[col]=pd.to_numeric(df[col],errors='coerce').fillna(0).astype(float).round(2)
    return df


def pct(a,b):
    return round(100*a/b,4) if b else 0.0


def processar(d):
    """Todas as transformacoes financeiras sao feitas no nivel item/pedido.
    A margem calculada e contribuicao estimada, nao lucro liquido contabil.
    """
    cli=d['clientes'].copy()
    cli['nome']=cli['nome'].astype(str).str.strip()
    cli['cidade']=cli['cidade'].astype(str).str.strip().str.title()
    cli['uf']=cli['uf'].astype(str).str.strip().str.upper()
    cli['email']=cli['email'].astype('string').str.strip().str.lower()
    cli['email']=cli['email'].replace('',pd.NA)
    cli['data_cadastro']=pd.to_datetime(cli['data_cadastro']).dt.date
    cli=cli[['cliente_id','nome','email','data_cadastro','cidade','uf','regiao','segmento','canal_aquisicao']]

    cats=d['categorias'].copy()
    pro=d['produtos'].copy().merge(cats,on='categoria_id',validate='many_to_one')
    pro['ativo']=pro['ativo'].astype(str).str.strip().str.casefold().map({'sim':1,'não':0,'nao':0})
    assert pro['ativo'].notna().all(),'Produto com ativo invalido'
    pro=sanitize_money(pro,['preco_tabela','custo_unitario'])
    pro=pro[['produto_id','sku','nome_produto','categoria_id','categoria','departamento','marca','preco_tabela','custo_unitario','ativo']]

    camp=d['campanhas'].copy()
    for col in ['data_inicio','data_fim']:
        camp[col]=pd.to_datetime(camp[col]).dt.date
    camp=sanitize_money(camp,['investimento'])
    camp=camp[['campanha_id','nome_campanha','canal_marketing','data_inicio','data_fim','investimento']]

    ped=d['pedidos'].copy()
    ped['data_pedido']=pd.to_datetime(ped['data_pedido'])
    ped['data_id']=ped['data_pedido'].dt.date
    mapas={'entregue':'Entregue','enviado':'Enviado','em separacao':'Em separação','em separação':'Em separação','cancelado':'Cancelado','devolvido':'Devolvido'}
    ped['status_pedido']=normalize_text(ped['status_pedido']).map(mapas)
    if ped['status_pedido'].isna().any(): raise ValueError('Status de pedido desconhecido')
    ped['canal_venda']=ped['canal_venda'].astype(str).str.strip()
    pag=d['pagamentos'].copy()
    pag['status_pagamento']=normalize_text(pag['status_pagamento']).map({'aprovado':'Aprovado','pendente':'Pendente','estornado':'Estornado'})
    if pag['status_pagamento'].isna().any(): raise ValueError('Status de pagamento desconhecido')
    pag=sanitize_money(pag,['valor_pago'])
    pag=pag[['pedido_id','forma_pagamento','status_pagamento','valor_pago','parcelas']]
    ent=d['entregas'].copy()
    ent['data_entrega']=pd.to_datetime(ent['data_entrega'],errors='coerce')
    ent['data_envio']=pd.to_datetime(ent['data_envio'],errors='coerce')
    ent=sanitize_money(ent,['custo_frete'])
    ent=ent[['pedido_id','data_envio','data_entrega','custo_frete']]

    ped=ped.merge(pag,on='pedido_id',how='left',validate='one_to_one').merge(ent,on='pedido_id',how='left',validate='one_to_one')
    ped['pedido_elegivel']=(((ped['status_pedido'].isin(['Entregue','Enviado'])) & (ped['status_pagamento']=='Aprovado')) | (ped['status_pedido']=='Devolvido')).astype(int)
    ped['tempo_entrega_dias']=(ped['data_entrega'].dt.normalize()-ped['data_pedido'].dt.normalize()).dt.days
    ped['entrega_concluida']=ped['data_entrega'].notna().astype(int)
    ped['entrega_atrasada']=((ped['tempo_entrega_dias']>ped['prazo_estimado_dias']) & ped['entrega_concluida'].eq(1)).astype(int)
    ped['custo_frete']=ped['custo_frete'].fillna(0).round(2)
    ped['valor_pago']=ped['valor_pago'].fillna(0).round(2)
    ped['receita_frete']=np.where(ped['pedido_elegivel'].eq(1),pd.to_numeric(ped['valor_frete']),0).round(2)
    ped['custo_frete']=np.where(ped['pedido_elegivel'].eq(1),ped['custo_frete'],0).round(2)

    items=d['itens_pedido'].copy()
    items=sanitize_money(items,['preco_unitario','desconto_unitario','custo_unitario_venda'])
    devol=d['devolucoes'].copy()
    devol=sanitize_money(devol,['valor_reembolso'])
    devol_agg=devol.groupby('item_id',as_index=False).agg(quantidade_devolvida=('quantidade','sum'),valor_devolvido=('valor_reembolso','sum'))
    items=items.merge(devol_agg,on='item_id',how='left',validate='one_to_one')
    items[['quantidade_devolvida','valor_devolvido']]=items[['quantidade_devolvida','valor_devolvido']].fillna(0)
    if (items['quantidade_devolvida']>items['quantidade']).any(): raise ValueError('Devolucao acima da quantidade vendida')
    items=items.merge(ped[['pedido_id','cliente_id','campanha_id','data_id','canal_venda','status_pedido','pedido_elegivel']],on='pedido_id',validate='many_to_one')
    eleg=items['pedido_elegivel']
    items['receita_bruta']=(items['quantidade']*items['preco_unitario']*eleg).round(2)
    items['desconto']=(items['quantidade']*items['desconto_unitario']*eleg).round(2)
    items['valor_devolvido']=(items['valor_devolvido']*eleg).round(2)
    items['cmv_bruto']=(items['quantidade']*items['custo_unitario_venda']*eleg).round(2)
    items['cmv_devolvido']=(items['quantidade_devolvida']*items['custo_unitario_venda']*eleg).round(2)
    items['cmv_liquido']=(items['cmv_bruto']-items['cmv_devolvido']).round(2)
    items['receita_produtos_liquida']=(items['receita_bruta']-items['desconto']-items['valor_devolvido']).round(2)
    items['margem_produtos']=(items['receita_produtos_liquida']-items['cmv_liquido']).round(2)
    items['quantidade_devolvida']=items['quantidade_devolvida'].astype(int)
    items=items[['item_id','pedido_id','cliente_id','produto_id','campanha_id','data_id','canal_venda','status_pedido','pedido_elegivel','quantidade','quantidade_devolvida','receita_bruta','desconto','valor_devolvido','receita_produtos_liquida','cmv_bruto','cmv_devolvido','cmv_liquido','margem_produtos']]

    tmp=items.assign(qtde_itens=items['quantidade']*items['pedido_elegivel'])
    somas=tmp.groupby('pedido_id',as_index=False).agg(qtde_itens=('qtde_itens','sum'),qtde_devolvida=('quantidade_devolvida','sum'),receita_bruta=('receita_bruta','sum'),descontos=('desconto','sum'),valor_devolvido=('valor_devolvido','sum'),receita_produtos_liquida=('receita_produtos_liquida','sum'),cmv_liquido=('cmv_liquido','sum'))
    ped=ped.merge(somas,on='pedido_id',validate='one_to_one')
    ped['receita_total_liquida']=(ped['receita_produtos_liquida']+ped['receita_frete']).round(2)
    ped['margem_contribuicao']=(ped['receita_total_liquida']-ped['cmv_liquido']-ped['custo_frete']).round(2)
    ped=ped[['pedido_id','cliente_id','campanha_id','data_id','data_pedido','status_pedido','canal_venda','forma_pagamento','status_pagamento','parcelas','valor_pago','pedido_elegivel','qtde_itens','qtde_devolvida','receita_bruta','descontos','valor_devolvido','receita_produtos_liquida','receita_frete','custo_frete','cmv_liquido','receita_total_liquida','margem_contribuicao','prazo_estimado_dias','entrega_concluida','tempo_entrega_dias','entrega_atrasada']]

    traf=d['trafego_diario'].copy().rename(columns={'data_referencia':'data_id'})
    traf['data_id']=pd.to_datetime(traf['data_id']).dt.date
    traf=traf[['data_id','canal_venda','sessoes','usuarios','visitas_produto','adicoes_carrinho','checkouts']]

    # Datas suficientes para todas as analises de tendencia/tempo
    inicio=pd.Timestamp(min(ped['data_id'])); fim=pd.Timestamp(max(ped['data_id']))
    fim=pd.Timestamp(year=fim.year,month=12,day=31)
    calendario=pd.DataFrame({'data_id':pd.date_range(inicio,fim,freq='D')})
    nomes=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
    calendario['ano']=calendario['data_id'].dt.year
    calendario['mes']=calendario['data_id'].dt.month
    calendario['ano_mes']=calendario['data_id'].dt.strftime('%Y-%m')
    calendario['trimestre']=calendario['data_id'].dt.quarter
    calendario['nome_mes']=calendario['mes'].map(lambda m:nomes[m-1])
    calendario['dia_semana']=calendario['data_id'].dt.weekday+1
    calendario['fim_semana']=(calendario['dia_semana']>=6).astype(int)
    calendario['data_id']=calendario['data_id'].dt.date

    ped['ano_mes']=pd.to_datetime(ped['data_id']).dt.strftime('%Y-%m')
    traf['ano_mes']=pd.to_datetime(traf['data_id']).dt.strftime('%Y-%m')
    res=[]
    traf_m=traf.groupby('ano_mes')['sessoes'].sum().to_dict()
    for mes,g in ped.groupby('ano_mes',sort=True):
        valid=g[g['pedido_elegivel']==1]
        receita=round(g['receita_total_liquida'].sum(),2)
        concl=int(g['entrega_concluida'].sum())
        vendidos=int(g['qtde_itens'].sum())
        sessoes=int(traf_m.get(mes,0))
        res.append(dict(ano_mes=mes,pedidos_totais=len(g),pedidos_validos=len(valid),pedidos_cancelados=int((g['status_pedido']=='Cancelado').sum()),clientes_ativos=valid['cliente_id'].nunique(),unidades_vendidas=vendidos,unidades_devolvidas=int(g['qtde_devolvida'].sum()),entregas_concluidas=concl,entregas_atrasadas=int(g['entrega_atrasada'].sum()),receita_bruta=round(g['receita_bruta'].sum(),2),descontos=round(g['descontos'].sum(),2),devolucoes=round(g['valor_devolvido'].sum(),2),receita_produtos_liquida=round(g['receita_produtos_liquida'].sum(),2),receita_frete=round(g['receita_frete'].sum(),2),receita_total_liquida=receita,cmv_liquido=round(g['cmv_liquido'].sum(),2),custo_frete=round(g['custo_frete'].sum(),2),margem_contribuicao=round(g['margem_contribuicao'].sum(),2),ticket_medio=round(receita/len(valid),2) if len(valid) else 0,margem_pct=pct(g['margem_contribuicao'].sum(),receita),taxa_devolucao_pct=pct(g['qtde_devolvida'].sum(),vendidos),taxa_cancelamento_pct=pct((g['status_pedido']=='Cancelado').sum(),len(g)),taxa_atraso_pct=pct(g['entrega_atrasada'].sum(),concl),sessoes=sessoes,taxa_conversao_pct=pct(len(valid),sessoes)))
    mensais=pd.DataFrame(res)

    ic=items.copy()
    ic['ano_mes']=pd.to_datetime(ic['data_id']).dt.strftime('%Y-%m')
    ic=ic.merge(pro[['produto_id','categoria_id','categoria']],on='produto_id',validate='many_to_one')
    ic['unidades_vendidas']=ic['quantidade']*ic['pedido_elegivel']
    cat_m=ic.groupby(['ano_mes','categoria_id','categoria'],as_index=False).agg(unidades_vendidas=('unidades_vendidas','sum'),receita_liquida=('receita_produtos_liquida','sum'),margem_produtos=('margem_produtos','sum'))
    for x in ['receita_liquida','margem_produtos']: cat_m[x]=cat_m[x].round(2)

    atribu=ped[(ped['pedido_elegivel']==1)&ped['campanha_id'].notna()]
    atribu=atribu.groupby('campanha_id',as_index=False).agg(pedidos_validos=('pedido_id','count'),receita_atribuida=('receita_total_liquida','sum'),margem_atribuida=('margem_contribuicao','sum'))
    campanhas=camp[['campanha_id','nome_campanha','canal_marketing','investimento']].merge(atribu,on='campanha_id',how='left',validate='one_to_one')
    for col in ['pedidos_validos','receita_atribuida','margem_atribuida']:
        campanhas[col]=campanhas[col].fillna(0)
    campanhas['pedidos_validos']=campanhas['pedidos_validos'].astype(int)
    campanhas['receita_atribuida']=campanhas['receita_atribuida'].round(2)
    campanhas['margem_atribuida']=campanhas['margem_atribuida'].round(2)
    campanhas['roas']=(campanhas['receita_atribuida']/campanhas['investimento'].replace(0,np.nan)).fillna(0).round(4)

    comprado=ped[(ped['pedido_elegivel']==1) & (ped['receita_produtos_liquida']>0)]
    rfm_agg=comprado.groupby('cliente_id',as_index=False).agg(data_ultima_compra=('data_id','max'),frequencia_pedidos=('pedido_id','count'),valor_monetario=('receita_total_liquida','sum'))
    rfm=cli[['cliente_id']].merge(rfm_agg,on='cliente_id',how='left',validate='one_to_one')
    referencia=max(ped['data_id'])  # recencia em relacao a ultima data do conjunto de dados
    rfm['recencia_dias']=rfm['data_ultima_compra'].apply(lambda x:(referencia-x).days if pd.notna(x) else np.nan)
    rfm['frequencia_pedidos']=rfm['frequencia_pedidos'].fillna(0).astype(int)
    rfm['valor_monetario']=rfm['valor_monetario'].fillna(0).round(2)
    rfm['score_r']=0; rfm['score_f']=0; rfm['score_m']=0
    mask=rfm['frequencia_pedidos']>0
    if mask.any():
        # scores por percentil: 5=maior valor/frequencia, ou menor recencia
        rfm.loc[mask,'score_r']=np.ceil(5*rfm.loc[mask,'recencia_dias'].rank(pct=True,ascending=False)).astype(int)
        rfm.loc[mask,'score_f']=np.ceil(5*rfm.loc[mask,'frequencia_pedidos'].rank(pct=True,ascending=True)).astype(int)
        rfm.loc[mask,'score_m']=np.ceil(5*rfm.loc[mask,'valor_monetario'].rank(pct=True,ascending=True)).astype(int)
    def segmento(r):
        if r['frequencia_pedidos']==0: return 'Sem compra'
        if r['score_r']>=4 and r['score_f']>=4 and r['score_m']>=4: return 'Campeões'
        if r['score_r']<=2 and r['score_f']>=3: return 'Em risco'
        if r['score_f']>=4: return 'Fiéis'
        if r['score_r']>=4: return 'Recentes'
        return 'Ocasionais'
    rfm['segmento_rfm']=rfm.apply(segmento,axis=1)
    rfm=rfm[['cliente_id','data_ultima_compra','recencia_dias','frequencia_pedidos','valor_monetario','score_r','score_f','score_m','segmento_rfm']]

    # Testes de reconciliacao fazem parte da rotina de processamento.
    assert len(ped)==len(d['pedidos']),'Quantidade de pedidos alterada'
    assert len(items)==len(d['itens_pedido']),'Quantidade de itens alterada'
    assert abs(ped['receita_produtos_liquida'].sum()-items['receita_produtos_liquida'].sum())<.01
    assert abs(ped['receita_total_liquida'].sum()-mensais['receita_total_liquida'].sum())<.01
    assert (ped['receita_produtos_liquida']>=-.01).all(),'Receita negativa por pedido'
    assert not (items['quantidade_devolvida']>items['quantidade']).any()
    assert (rfm['score_r'].between(0,5)&rfm['score_f'].between(0,5)&rfm['score_m'].between(0,5)).all()

    return {
        'DimCliente':cli,'DimProduto':pro,'DimCampanha':camp,'DimCalendario':calendario,
        'FatoPedidos':ped.drop(columns='ano_mes'),'FatoItensPedido':items,
        'FatoTrafegoDiario':traf.drop(columns='ano_mes'),
        'IndicadoresMensais':mensais,'DesempenhoCategorias':cat_m,
        'DesempenhoCampanhas':campanhas,'ClientesRFM':rfm
    }


def exportar_csv(tabelas):
    OUT.mkdir(parents=True,exist_ok=True)
    for nome,df in tabelas.items():
        df.to_csv(OUT/f'{nome}.csv',sep=';',index=False,encoding='utf-8-sig',date_format='%Y-%m-%d')
        print(f'analytics.{nome:<22} {len(df):>7,} linhas')



def main():
    """Reprocessa os dados brutos e reconstrói os 11 CSVs analíticos.
    Requer pandas e numpy (pip install -r backend/requirements.txt).
    """
    print('Processando dados brutos com pandas e numpy...')
    tabelas=processar(capturar_offline())
    exportar_csv(tabelas)
    m=tabelas['IndicadoresMensais']
    print(f"TOTAL receita: R$ {m['receita_total_liquida'].sum():,.2f} | Pedidos validos: {m['pedidos_validos'].sum():,}")
    print('Em seguida, execute criar_banco_sqlite.py e gerar_dashboard.py')

if __name__=='__main__': main()
