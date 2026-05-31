import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import zipfile
import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Analisador de NF-e", layout="wide")

st.title("📊 Analisador Inteligente de NF-e por SKU")
st.write("Navegue pelos separadores abaixo para analisar Vendas, Entradas e Impostos. Suporta histórico acumulado!")

# --- CONTROLES DE SESSÃO ---
if "upload_key_saidas" not in st.session_state: st.session_state.upload_key_saidas = 0
if "upload_key_entradas" not in st.session_state: st.session_state.upload_key_entradas = 0
if "upload_key_impostos" not in st.session_state: st.session_state.upload_key_impostos = 0

def limpar_uploads_saidas(): st.session_state.upload_key_saidas += 1
def limpar_uploads_entradas(): st.session_state.upload_key_entradas += 1
def limpar_uploads_impostos(): st.session_state.upload_key_impostos += 1

# --- FUNÇÕES NÚCLEO (Extração de XML) ---
def extrair_dados_xml(arquivo_lido, tipo_nota, nome_arquivo, chaves_processadas, contadores):
    dados_extraidos = []
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    
    try:
        tree = ET.parse(arquivo_lido)
        root = tree.getroot()
        
        inf_nfe = root.find('.//nfe:infNFe', ns)
        if inf_nfe is not None and 'Id' in inf_nfe.attrib:
            chave_acesso = inf_nfe.attrib['Id']
        else:
            chave_acesso = nome_arquivo
            
        if chave_acesso in chaves_processadas:
            contadores['duplicatas'] += 1
            return [] 
            
        chaves_processadas.add(chave_acesso)
        
        data_emissao_str = None
        ide = root.find('.//nfe:ide', ns)
        if ide is not None:
            dh_emi = ide.find('nfe:dhEmi', ns)
            d_emi = ide.find('nfe:dEmi', ns)
            
            data_bruta = None
            if dh_emi is not None: data_bruta = dh_emi.text.split('T')[0]
            elif d_emi is not None: data_bruta = d_emi.text.split('T')[0]
                
            if data_bruta and len(data_bruta) == 10:
                data_emissao_str = data_bruta
        
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            imposto = det.find('nfe:imposto', ns)
            
            if prod is not None:
                sku_node = prod.find('nfe:cProd', ns)
                qtd_node = prod.find('nfe:qCom', ns)
                desc_node = prod.find('nfe:xProd', ns)
                vprod_node = prod.find('nfe:vProd', ns)
                
                # Inicializa impostos zerados
                v_icms, v_pis, v_cofins = 0.0, 0.0, 0.0
                
                # Busca os impostos se a tag existir
                if imposto is not None:
                    icms_node = imposto.find('.//nfe:vICMS', ns)
                    pis_node = imposto.find('.//nfe:vPIS', ns)
                    cofins_node = imposto.find('.//nfe:vCOFINS', ns)
                    
                    if icms_node is not None: v_icms = float(icms_node.text)
                    if pis_node is not None: v_pis = float(pis_node.text)
                    if cofins_node is not None: v_cofins = float(cofins_node.text)
                
                if sku_node is not None and qtd_node is not None:
                    sku = str(sku_node.text).strip()
                    quantidade = float(qtd_node.text)
                    descricao = desc_node.text if desc_node is not None else "Sem Descrição"
                    v_prod = float(vprod_node.text) if vprod_node is not None else 0.0
                    
                    dados_extraidos.append({
                        'DataEmissaoRaw': data_emissao_str,
                        'SKU': sku,
                        'Descricao': descricao,
                        'Quantidade': quantidade,
                        'Valor Produto': v_prod,
                        'ICMS': v_icms,
                        'PIS': v_pis,
                        'COFINS': v_cofins,
                        'Tipo': tipo_nota
                    })
        
        if len(dados_extraidos) == 0:
            contadores['sem_sku'] += 1
            contadores['nomes_sem_sku'].append(nome_arquivo)
            
    except Exception as e:
        if not nome_arquivo.startswith('__MACOSX') and not nome_arquivo.startswith('.'):
            st.error(f"Erro ao ler o ficheiro {nome_arquivo}: {e}")
            
    return dados_extraidos

def processar_arquivos(lista_arquivos, tipo_nota, chaves_processadas, contadores):
    dados_finais = []
    for arquivo in lista_arquivos:
        if arquivo.name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(arquivo) as z:
                    for nome_arquivo_interno in z.namelist():
                        if nome_arquivo_interno.lower().endswith('.xml'):
                            with z.open(nome_arquivo_interno) as f:
                                dados_finais.extend(extrair_dados_xml(f, tipo_nota, nome_arquivo_interno, chaves_processadas, contadores))
            except Exception as e:
                st.error(f"Erro ao abrir o ficheiro ZIP {arquivo.name}: {e}")
        elif arquivo.name.lower().endswith('.xml'):
            dados_finais.extend(extrair_dados_xml(arquivo, tipo_nota, arquivo.name, chaves_processadas, contadores))
    return pd.DataFrame(dados_finais)

# ==========================================
# CRIAÇÃO DOS SEPARADORES (TABS)
# ==========================================
aba_saidas, aba_entradas, aba_impostos = st.tabs(["📉 Saídas (Vendas/Devoluções)", "📦 Entradas (Compras)", "💰 Impostos (Saídas)"])

# ------------------------------------------
# ABA 1: VENDAS E DEVOLUÇÕES (Código idêntico à versão anterior)
# ------------------------------------------
with aba_saidas:
    st.header("Análise de Saídas e Devoluções")
    st.subheader("🕰️ Passo 1: Histórico Anterior (Opcional)")
    historico_saidas = st.file_uploader("Ficheiro Excel de Histórico (Saídas)", type=['xlsx'], key=f"hist_saidas_{st.session_state.upload_key_saidas}")
    
    st.divider()
    st.subheader("📥 Passo 2: Novas Notas Fiscais")
    col1, col2 = st.columns(2)
    with col1: arquivos_venda = st.file_uploader("XMLs/ZIP de Venda", type=['xml', 'zip'], accept_multiple_files=True, key=f"vendas_{st.session_state.upload_key_saidas}")
    with col2: arquivos_devolucao = st.file_uploader("XMLs/ZIP de Devolução", type=['xml', 'zip'], accept_multiple_files=True, key=f"devolucoes_{st.session_state.upload_key_saidas}")

    st.divider()
    usar_filtro_data_saidas = st.checkbox("Filtrar Novas Notas por Data de Emissão", key="check_data_saidas")
    data_inicial_saidas, data_final_saidas = None, None
    if usar_filtro_data_saidas:
        col_d1, col_d2 = st.columns(2)
        with col_d1: data_inicial_saidas = st.date_input("Data Inicial", format="DD/MM/YYYY", key="d_ini_saidas")
        with col_d2: data_final_saidas = st.date_input("Data Final", format="DD/MM/YYYY", key="d_fim_saidas")

    st.divider()
    col_btn1, col_btn2 = st.columns([2, 8])
    with col_btn1: st.button("🗑️ Limpar Tudo", on_click=limpar_uploads_saidas, key="btn_limpar_saidas")
    with col_btn2: gerar_saidas = st.button("🚀 Gerar Relatório Atualizado", type="primary", key="btn_gerar_saidas")

    if gerar_saidas:
        with st.spinner("Processando dados..."):
            relatorio_saidas = pd.DataFrame()
            chaves_processadas_saidas = set()
            cont_saidas = {'duplicatas': 0, 'sem_sku': 0, 'nomes_sem_sku': []}
            
            if arquivos_venda or arquivos_devolucao:
                df_vendas = processar_arquivos(arquivos_venda, 'Venda', chaves_processadas_saidas, cont_saidas) if arquivos_venda else pd.DataFrame()
                df_devolucoes = processar_arquivos(arquivos_devolucao, 'Devolucao', chaves_processadas_saidas, cont_saidas) if arquivos_devolucao else pd.DataFrame()
                df_total_saidas = pd.concat([df_vendas, df_devolucoes])
                
                if not df_total_saidas.empty:
                    df_total_saidas['DataFormatada'] = pd.to_datetime(df_total_saidas['DataEmissaoRaw'], errors='coerce').dt.date
                    if usar_filtro_data_saidas:
                        df_total_saidas = df_total_saidas[(df_total_saidas['DataFormatada'] >= data_inicial_saidas) & (df_total_saidas['DataFormatada'] <= data_final_saidas)]
                    
                    if not df_total_saidas.empty:
                        df_descricoes_saidas = df_total_saidas.groupby(['SKU', 'Descricao'], as_index=False)['Quantidade'].sum()
                        df_melhor_desc_saidas = df_descricoes_saidas.sort_values(by=['SKU', 'Quantidade'], ascending=[True, False]).drop_duplicates(subset=['SKU'], keep='first')
                        
                        relatorio_saidas = pd.pivot_table(df_total_saidas, values='Quantidade', index='SKU', columns='Tipo', aggfunc='sum', fill_value=0).reset_index()
                        if 'Venda' not in relatorio_saidas.columns: relatorio_saidas['Venda'] = 0
                        if 'Devolucao' not in relatorio_saidas.columns: relatorio_saidas['Devolucao'] = 0
                        
                        relatorio_saidas = pd.merge(relatorio_saidas, df_melhor_desc_saidas[['SKU', 'Descricao']], on='SKU', how='left')
                        relatorio_saidas['SKU'] = relatorio_saidas['SKU'].astype(str)

            if historico_saidas is not None:
                df_hist = pd.read_excel(historico_saidas)
                for col in ['SKU', 'Descricao', 'Venda', 'Devolucao']:
                    if col not in df_hist.columns: df_hist[col] = 0 if col not in ['SKU', 'Descricao'] else 'Sem Dados'
                df_hist['SKU'] = df_hist['SKU'].astype(str)
                
                if not relatorio_saidas.empty:
                    relatorio_saidas = pd.merge(relatorio_saidas, df_hist, on='SKU', how='outer', suffixes=('_novo', '_hist'))
                    relatorio_saidas['Venda'] = relatorio_saidas['Venda_novo'].fillna(0) + relatorio_saidas['Venda_hist'].fillna(0)
                    relatorio_saidas['Devolucao'] = relatorio_saidas['Devolucao_novo'].fillna(0) + relatorio_saidas['Devolucao_hist'].fillna(0)
                    relatorio_saidas['Descricao'] = relatorio_saidas['Descricao_novo'].combine_first(relatorio_saidas['Descricao_hist'])
                else:
                    relatorio_saidas = df_hist.copy()

            if not relatorio_saidas.empty:
                for col in ['Venda', 'Devolucao']:
                    if col not in relatorio_saidas.columns: relatorio_saidas[col] = 0
                relatorio_saidas['Saldo Líquido'] = relatorio_saidas['Venda'] - relatorio_saidas['Devolucao']
                relatorio_saidas = relatorio_saidas[['SKU', 'Descricao', 'Venda', 'Devolucao', 'Saldo Líquido']].sort_values(by='Venda', ascending=False)
                st.dataframe(relatorio_saidas, use_container_width=True)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer: relatorio_saidas.to_excel(writer, index=False, sheet_name='Saidas_e_Devolucoes')
                st.download_button("💾 Baixar Excel Consolidado", data=buffer.getvalue(), file_name="relatorio_saidas_acumulado.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_saidas")

# ------------------------------------------
# ABA 2: NOTAS DE ENTRADA (COMPRAS)
# ------------------------------------------
with aba_entradas:
    st.header("Análise de Entradas (Compras)")
    
    st.subheader("🕰️ Passo 1: Histórico Anterior (Opcional)")
    st.info("Carregue a última planilha Excel de Entradas para acumular o inventário e manter o preço médio histórico.")
    historico_entradas = st.file_uploader("Ficheiro Excel de Histórico (Entradas)", type=['xlsx'], key=f"hist_entradas_{st.session_state.upload_key_entradas}")
    
    st.divider()
    st.subheader("📥 Passo 2: Novas Notas de Entrada")
    arquivos_entrada = st.file_uploader("XMLs ou ZIP de Entrada", type=['xml', 'zip'], accept_multiple_files=True, key=f"entradas_{st.session_state.upload_key_entradas}")

    st.divider()
    usar_filtro_data_entradas = st.checkbox("Filtrar Novas Notas por Data de Emissão", key="check_data_entradas")

    data_inicial_entradas, data_final_entradas = None, None
    if usar_filtro_data_entradas:
        col_d3, col_d4 = st.columns(2)
        with col_d3:
            data_inicial_entradas = st.date_input("Data Inicial", format="DD/MM/YYYY", key="d_ini_entradas")
        with col_d4:
            data_final_entradas = st.date_input("Data Final", format="DD/MM/YYYY", key="d_fim_entradas")
        if data_inicial_entradas > data_final_entradas:
            st.error("A Data Inicial não pode ser maior que a Data Final.")

    st.divider()
    col_btn3, col_btn4 = st.columns([2, 8])
    with col_btn3:
        st.button("🗑️ Limpar Tudo", on_click=limpar_uploads_entradas, key="btn_limpar_entradas")
    with col_btn4:
        gerar_entradas = st.button("🚀 Gerar Relatório Atualizado", type="primary", key="btn_gerar_entradas")

    if gerar_entradas:
        if not arquivos_entrada and not historico_entradas:
            st.warning("⚠️ Carregue novos XMLs ou pelo menos um histórico para continuar.")
        elif usar_filtro_data_entradas and data_inicial_entradas > data_final_entradas:
            st.error("Corrija o período das datas.")
        else:
            with st.spinner("Processando Notas, atualizando histórico e calculando preço médio..."):
                relatorio_entradas = pd.DataFrame()
                chaves_processadas_entradas = set()
                cont_entradas = {'duplicatas': 0, 'sem_sku': 0, 'nomes_sem_sku': []}
                
                # Processa os XMLs novos se existirem
                if arquivos_entrada:
                    df_entradas = processar_arquivos(arquivos_entrada, 'Entrada', chaves_processadas_entradas, cont_entradas)
                    
                    if not df_entradas.empty:
                        df_entradas['DataFormatada'] = pd.to_datetime(df_entradas['DataEmissaoRaw'], errors='coerce').dt.date
                        
                        if usar_filtro_data_entradas:
                            df_entradas = df_entradas[(df_entradas['DataFormatada'] >= data_inicial_entradas) & (df_entradas['DataFormatada'] <= data_final_entradas)]
                        
                        if not df_entradas.empty:
                            # AGORA SOMAMOS TAMBÉM O VALOR DO PRODUTO
                            df_total_sku = df_entradas.groupby('SKU', as_index=False)[['Quantidade', 'Valor Produto']].sum()
                            df_total_sku = df_total_sku.rename(columns={'Quantidade': 'Quantidade Comprada', 'Valor Produto': 'Valor Total Comprado'})
                            
                            df_descricoes = df_entradas.groupby(['SKU', 'Descricao'], as_index=False)['Quantidade'].sum()
                            df_melhor_descricao = df_descricoes.sort_values(by=['SKU', 'Quantidade'], ascending=[True, False]).drop_duplicates(subset=['SKU'], keep='first')
                            
                            relatorio_entradas = pd.merge(df_total_sku, df_melhor_descricao[['SKU', 'Descricao']], on='SKU')
                            relatorio_entradas['SKU'] = relatorio_entradas['SKU'].astype(str)

                # Unir com o Histórico
                if historico_entradas is not None:
                    try:
                        df_hist_ent = pd.read_excel(historico_entradas)
                        
                        # Garante que as colunas antigas existam, adicionando o Valor Total para o cálculo do preço médio
                        for col in ['SKU', 'Descricao', 'Quantidade Comprada', 'Valor Total Comprado']:
                            if col not in df_hist_ent.columns:
                                df_hist_ent[col] = 0.0 if col not in ['Descricao', 'SKU'] else 'Sem Dados'
                        
                        df_hist_ent['SKU'] = df_hist_ent['SKU'].astype(str)
                        
                        if not relatorio_entradas.empty:
                            relatorio_entradas = pd.merge(relatorio_entradas, df_hist_ent, on='SKU', how='outer', suffixes=('_novo', '_hist'))
                            relatorio_entradas['Quantidade Comprada'] = relatorio_entradas['Quantidade Comprada_novo'].fillna(0) + relatorio_entradas['Quantidade Comprada_hist'].fillna(0)
                            relatorio_entradas['Valor Total Comprado'] = relatorio_entradas['Valor Total Comprado_novo'].fillna(0) + relatorio_entradas['Valor Total Comprado_hist'].fillna(0)
                            relatorio_entradas['Descricao'] = relatorio_entradas['Descricao_novo'].combine_first(relatorio_entradas['Descricao_hist'])
                        else:
                            relatorio_entradas = df_hist_ent.copy()
                    except Exception as e:
                        st.error(f"Erro ao ler o histórico: {e}")

                # Finaliza o Relatório e Calcula a Média
                if not relatorio_entradas.empty:
                    if 'Quantidade Comprada' not in relatorio_entradas.columns: relatorio_entradas['Quantidade Comprada'] = 0
                    if 'Valor Total Comprado' not in relatorio_entradas.columns: relatorio_entradas['Valor Total Comprado'] = 0.0
                    
                    # CALCULA O PREÇO MÉDIO DE ENTRADA (Valor Total / Quantidade)
                    relatorio_entradas['Preço Médio de Entrada'] = relatorio_entradas.apply(
                        lambda row: row['Valor Total Comprado'] / row['Quantidade Comprada'] if row['Quantidade Comprada'] > 0 else 0, 
                        axis=1
                    )
                    
                    # Arredonda para 2 casas decimais (formato moeda)
                    relatorio_entradas['Preço Médio de Entrada'] = relatorio_entradas['Preço Médio de Entrada'].round(2)
                    relatorio_entradas['Valor Total Comprado'] = relatorio_entradas['Valor Total Comprado'].round(2)
                    
                    # Reordena as colunas para o Excel final
                    relatorio_entradas = relatorio_entradas[['SKU', 'Descricao', 'Quantidade Comprada', 'Valor Total Comprado', 'Preço Médio de Entrada']]
                    relatorio_entradas = relatorio_entradas.sort_values(by='Quantidade Comprada', ascending=False)
                    
                    st.success(f"✅ Inventário atualizado e preços médios calculados com sucesso!")
                    if cont_entradas['sem_sku'] > 0: st.warning(f"⚠️ {cont_entradas['sem_sku']} XMLs ignorados por não terem produtos.")
                            
                    st.dataframe(relatorio_entradas, use_container_width=True)
                    
                    buffer_ent = io.BytesIO()
                    with pd.ExcelWriter(buffer_ent, engine='openpyxl') as writer:
                        relatorio_entradas.to_excel(writer, index=False, sheet_name='Entradas')
                    
                    st.download_button("💾 Baixar Excel Consolidado", data=buffer_ent.getvalue(), file_name="relatorio_entradas_acumulado.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_entradas")
                else:
                    st.error("❌ Nenhum dado válido encontrado para gerar o relatório.")

# ------------------------------------------
# ABA 3: IMPOSTOS (SAÍDAS) - NOVA ABA!
# ------------------------------------------
with aba_impostos:
    st.header("Análise de Impostos (Saídas)")
    st.write("Suba os XMLs das suas notas de saída para extrair os valores totais de ICMS, PIS e COFINS cobrados por cada SKU.")
    
    st.subheader("🕰️ Passo 1: Histórico Anterior (Opcional)")
    historico_impostos = st.file_uploader(
        "Ficheiro Excel de Histórico (Impostos)", 
        type=['xlsx'], 
        key=f"hist_impostos_{st.session_state.upload_key_impostos}"
    )
    
    st.divider()
    st.subheader("📥 Passo 2: Novas Notas Fiscais de Venda/Saída")
    arquivos_impostos = st.file_uploader(
        "XMLs ou ZIP de Saídas", 
        type=['xml', 'zip'], 
        accept_multiple_files=True, 
        key=f"impostos_{st.session_state.upload_key_impostos}"
    )

    st.divider()
    usar_filtro_data_impostos = st.checkbox("Filtrar Novas Notas por Data de Emissão", key="check_data_impostos")
    data_inicial_impostos, data_final_impostos = None, None
    
    if usar_filtro_data_impostos:
        col_d5, col_d6 = st.columns(2)
        with col_d5: 
            data_inicial_impostos = st.date_input(
                "Data Inicial", 
                format="DD/MM/YYYY", 
                key="d_ini_impostos"
            )
        with col_d6: 
            data_final_impostos = st.date_input(
                "Data Final", 
                format="DD/MM/YYYY", 
                key="d_fim_impostos"
            )

    st.divider()
    col_btn5, col_btn6 = st.columns([2, 8])
    with col_btn5: 
        st.button("🗑️ Limpar Tudo", on_click=limpar_uploads_impostos, key="btn_limpar_impostos")
    with col_btn6: 
        gerar_impostos = st.button("🚀 Gerar Relatório de Impostos", type="primary", key="btn_gerar_impostos")

    if gerar_impostos:
        if not arquivos_impostos and not historico_impostos:
            st.warning("⚠️ Carregue novos XMLs ou pelo menos um histórico para continuar.")
        elif usar_filtro_data_impostos and data_inicial_impostos > data_final_impostos:
            st.error("Corrija o período das datas.")
        else:
            with st.spinner("Extraindo bases de cálculo e impostos (ICMS, PIS, COFINS)..."):
                relatorio_impostos = pd.DataFrame()
                chaves_processadas_impostos = set()
                cont_impostos = {'duplicatas': 0, 'sem_sku': 0, 'nomes_sem_sku': []}
                
                # Processa os XMLs novos
                if arquivos_impostos:
                    df_impostos = processar_arquivos(arquivos_impostos, 'Saida', chaves_processadas_impostos, cont_impostos)
                    
                    if not df_impostos.empty:
                        df_impostos['DataFormatada'] = pd.to_datetime(df_impostos['DataEmissaoRaw'], errors='coerce').dt.date
                        
                        if usar_filtro_data_impostos:
                            df_impostos = df_impostos[(df_impostos['DataFormatada'] >= data_inicial_impostos) & (df_impostos['DataFormatada'] <= data_final_impostos)]
                        
                        if not df_impostos.empty:
                            # Agrupa por SKU e Descrição, somando Quantidade, Valor e os 3 impostos
                            df_imp_agrupado = df_impostos.groupby(['SKU', 'Descricao'], as_index=False)[['Quantidade', 'Valor Produto', 'ICMS', 'PIS', 'COFINS']].sum()
                            
                            # Filtra a melhor descrição
                            df_melhor_desc_imp = df_imp_agrupado.sort_values(by=['SKU', 'Quantidade'], ascending=[True, False]).drop_duplicates(subset=['SKU'], keep='first')
                            
                            relatorio_impostos = df_melhor_desc_imp.copy()
                            relatorio_impostos['SKU'] = relatorio_impostos['SKU'].astype(str)

                # Unir com o Histórico
                if historico_impostos is not None:
                    try:
                        df_hist_imp = pd.read_excel(historico_impostos)
                        colunas_necessarias = ['SKU', 'Descricao', 'Quantidade', 'Valor Produto', 'ICMS', 'PIS', 'COFINS']
                        for col in colunas_necessarias:
                            if col not in df_hist_imp.columns:
                                df_hist_imp[col] = 0 if col != 'Descricao' else 'Sem Dados'
                        
                        df_hist_imp['SKU'] = df_hist_imp['SKU'].astype(str)
                        
                        if not relatorio_impostos.empty:
                            relatorio_impostos = pd.merge(relatorio_impostos, df_hist_imp, on='SKU', how='outer', suffixes=('_novo', '_hist'))
                            for col in ['Quantidade', 'Valor Produto', 'ICMS', 'PIS', 'COFINS']:
                                relatorio_impostos[col] = relatorio_impostos[f'{col}_novo'].fillna(0) + relatorio_impostos[f'{col}_hist'].fillna(0)
                            relatorio_impostos['Descricao'] = relatorio_impostos['Descricao_novo'].combine_first(relatorio_impostos['Descricao_hist'])
                        else:
                            relatorio_impostos = df_hist_imp.copy()
                    except Exception as e:
                        st.error(f"Erro ao ler o histórico: {e}")

                # Finaliza o Relatório
                if not relatorio_impostos.empty:
                    relatorio_impostos = relatorio_impostos[['SKU', 'Descricao', 'Quantidade', 'Valor Produto', 'ICMS', 'PIS', 'COFINS']]
                    relatorio_impostos = relatorio_impostos.sort_values(by='Valor Produto', ascending=False)
                    
                    st.success(f"✅ Impostos extraídos com sucesso de {len(chaves_processadas_impostos) - cont_impostos['sem_sku']} notas válidas.")
                            
                    st.dataframe(relatorio_impostos, use_container_width=True)
                    
                    buffer_imp = io.BytesIO()
                    with pd.ExcelWriter(buffer_imp, engine='openpyxl') as writer:
                        relatorio_impostos.to_excel(writer, index=False, sheet_name='Impostos')
                    
                    st.download_button("💾 Baixar Excel de Impostos", data=buffer_imp.getvalue(), file_name="relatorio_impostos_saida.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_impostos")
                else:
                    st.error("❌ Nenhum dado válido encontrado para gerar o relatório.")
