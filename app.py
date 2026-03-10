import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import zipfile
import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Analisador de NF-e", layout="wide")

st.title("📊 Analisador Inteligente de NF-e por SKU")
st.write("Navegue pelas abas abaixo para analisar suas Vendas/Devoluções ou suas Notas de Entrada (Compras).")

# --- CONTROLES DE SESSÃO (Para limpar arquivos independentemente) ---
if "upload_key_saidas" not in st.session_state:
    st.session_state.upload_key_saidas = 0
if "upload_key_entradas" not in st.session_state:
    st.session_state.upload_key_entradas = 0

def limpar_uploads_saidas():
    st.session_state.upload_key_saidas += 1

def limpar_uploads_entradas():
    st.session_state.upload_key_entradas += 1

# --- FUNÇÕES NÚCLEO (Extração de XML) ---
def extrair_dados_xml(arquivo_lido, tipo_nota, nome_arquivo, chaves_processadas, contadores):
    dados_extraidos = []
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    
    try:
        tree = ET.parse(arquivo_lido)
        root = tree.getroot()
        
        # 1. Chave de Acesso
        inf_nfe = root.find('.//nfe:infNFe', ns)
        if inf_nfe is not None and 'Id' in inf_nfe.attrib:
            chave_acesso = inf_nfe.attrib['Id']
        else:
            chave_acesso = nome_arquivo
            
        # 2. Evita duplicidade
        if chave_acesso in chaves_processadas:
            contadores['duplicatas'] += 1
            return [] 
            
        chaves_processadas.add(chave_acesso)
        
        # 3. Data de Emissão
        data_emissao_str = None
        ide = root.find('.//nfe:ide', ns)
        if ide is not None:
            dh_emi = ide.find('nfe:dhEmi', ns)
            d_emi = ide.find('nfe:dEmi', ns)
            
            data_bruta = None
            if dh_emi is not None:
                data_bruta = dh_emi.text.split('T')[0]
            elif d_emi is not None:
                data_bruta = d_emi.text.split('T')[0]
                
            if data_bruta and len(data_bruta) == 10:
                data_emissao_str = data_bruta
        
        # 4. Itens da Nota
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            if prod is not None:
                sku_node = prod.find('nfe:cProd', ns)
                qtd_node = prod.find('nfe:qCom', ns)
                
                if sku_node is not None and qtd_node is not None:
                    sku = sku_node.text
                    quantidade = float(qtd_node.text)
                    
                    dados_extraidos.append({
                        'DataEmissaoRaw': data_emissao_str,
                        'SKU': sku,
                        'Quantidade': quantidade,
                        'Tipo': tipo_nota
                    })
        
        if len(dados_extraidos) == 0:
            contadores['sem_sku'] += 1
            contadores['nomes_sem_sku'].append(nome_arquivo)
            
    except Exception as e:
        if not nome_arquivo.startswith('__MACOSX') and not nome_arquivo.startswith('.'):
            st.error(f"Erro ao ler o arquivo {nome_arquivo}: {e}")
            
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
                st.error(f"Erro ao abrir o arquivo ZIP {arquivo.name}: {e}")
        elif arquivo.name.lower().endswith('.xml'):
            dados_finais.extend(extrair_dados_xml(arquivo, tipo_nota, arquivo.name, chaves_processadas, contadores))
    return pd.DataFrame(dados_finais)

# ==========================================
# CRIAÇÃO DAS ABAS (TABS)
# ==========================================
aba_saidas, aba_entradas = st.tabs(["📉 Saídas (Vendas e Devoluções)", "📦 Entradas (Compras)"])

# ------------------------------------------
# ABA 1: VENDAS E DEVOLUÇÕES
# ------------------------------------------
with aba_saidas:
    st.header("Análise de Saídas e Devoluções")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📥 Notas de Venda")
        arquivos_venda = st.file_uploader("XMLs/ZIP de Venda", type=['xml', 'zip'], accept_multiple_files=True, key=f"vendas_{st.session_state.upload_key_saidas}")

    with col2:
        st.subheader("📤 Notas de Devolução")
        arquivos_devolucao = st.file_uploader("XMLs/ZIP de Devolução", type=['xml', 'zip'], accept_multiple_files=True, key=f"devolucoes_{st.session_state.upload_key_saidas}")

    st.divider()
    st.subheader("📅 Filtro de Período (Opcional)")
    usar_filtro_data_saidas = st.checkbox("Filtrar resultados por Data de Emissão", key="check_data_saidas")

    data_inicial_saidas, data_final_saidas = None, None
    if usar_filtro_data_saidas:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            data_inicial_saidas = st.date_input("Data Inicial", format="DD/MM/YYYY", key="d_ini_saidas")
        with col_d2:
            data_final_saidas = st.date_input("Data Final", format="DD/MM/YYYY", key="d_fim_saidas")
        if data_inicial_saidas > data_final_saidas:
            st.error("A Data Inicial não pode ser maior que a Data Final.")

    st.divider()
    col_btn1, col_btn2 = st.columns([2, 8])
    with col_btn1:
        st.button("🗑️ Limpar Arquivos", on_click=limpar_uploads_saidas, key="btn_limpar_saidas")
    with col_btn2:
        gerar_saidas = st.button("🚀 Gerar Relatório de Vendas/Devoluções", type="primary", key="btn_gerar_saidas")

    if gerar_saidas:
        if not arquivos_venda and not arquivos_devolucao:
            st.warning("⚠️ Faça o upload de pelo menos um arquivo para continuar.")
        elif usar_filtro_data_saidas and data_inicial_saidas > data_final_saidas:
            st.error("Corrija o período das datas.")
        else:
            with st.spinner("Processando Vendas e Devoluções..."):
                chaves_processadas_saidas = set()
                cont_saidas = {'duplicatas': 0, 'sem_sku': 0, 'nomes_sem_sku': []}
                
                df_vendas = processar_arquivos(arquivos_venda, 'Venda', chaves_processadas_saidas, cont_saidas) if arquivos_venda else pd.DataFrame()
                df_devolucoes = processar_arquivos(arquivos_devolucao, 'Devolucao', chaves_processadas_saidas, cont_saidas) if arquivos_devolucao else pd.DataFrame()
                
                df_total_saidas = pd.concat([df_vendas, df_devolucoes])
                
                if not df_total_saidas.empty:
                    df_total_saidas['DataFormatada'] = pd.to_datetime(df_total_saidas['DataEmissaoRaw'], errors='coerce').dt.date
                    
                    if usar_filtro_data_saidas:
                        df_total_saidas = df_total_saidas[(df_total_saidas['DataFormatada'] >= data_inicial_saidas) & (df_total_saidas['DataFormatada'] <= data_final_saidas)]
                    
                    if df_total_saidas.empty:
                        st.warning("Nenhum produto encontrado no período selecionado.")
                    else:
                        relatorio_saidas = pd.pivot_table(df_total_saidas, values='Quantidade', index='SKU', columns='Tipo', aggfunc='sum', fill_value=0).reset_index()
                        
                        if 'Venda' not in relatorio_saidas.columns: relatorio_saidas['Venda'] = 0
                        if 'Devolucao' not in relatorio_saidas.columns: relatorio_saidas['Devolucao'] = 0
                            
                        relatorio_saidas['Saldo Líquido'] = relatorio_saidas['Venda'] - relatorio_saidas['Devolucao']
                        relatorio_saidas = relatorio_saidas.sort_values(by='Venda', ascending=False)
                        
                        st.success(f"✅ Sucesso! Lidas {len(chaves_processadas_saidas) - cont_saidas['sem_sku']} notas válidas.")
                        if cont_saidas['duplicatas'] > 0: st.warning(f"🔄 Ignorados {cont_saidas['duplicatas']} arquivos repetidos.")
                        if cont_saidas['sem_sku'] > 0:
                            st.error(f"⚠️ {cont_saidas['sem_sku']} arquivos sem produtos.")
                            with st.expander("👀 Ver arquivos"):
                                for arq in cont_saidas['nomes_sem_sku']: st.write(f"- {arq}")
                        
                        st.dataframe(relatorio_saidas, use_container_width=True)
                        
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            relatorio_saidas.to_excel(writer, index=False, sheet_name='Saidas_e_Devolucoes')
                        
                        st.download_button("💾 Baixar Excel (Vendas)", data=buffer.getvalue(), file_name="relatorio_saidas.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_saidas")
                else:
                    st.error("❌ Nenhum dado válido encontrado.")

# ------------------------------------------
# ABA 2: NOTAS DE ENTRADA (COMPRAS)
# ------------------------------------------
with aba_entradas:
    st.header("Análise de Entradas (Compras)")
    st.write("Suba os XMLs dos seus fornecedores para agrupar as quantidades recebidas de cada SKU.")
    
    arquivos_entrada = st.file_uploader("Selecione os XMLs ou um ZIP de Entrada", type=['xml', 'zip'], accept_multiple_files=True, key=f"entradas_{st.session_state.upload_key_entradas}")

    st.divider()
    st.subheader("📅 Filtro de Período (Opcional)")
    usar_filtro_data_entradas = st.checkbox("Filtrar resultados por Data de Emissão", key="check_data_entradas")

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
        st.button("🗑️ Limpar Arquivos", on_click=limpar_uploads_entradas, key="btn_limpar_entradas")
    with col_btn4:
        gerar_entradas = st.button("🚀 Gerar Relatório de Entradas", type="primary", key="btn_gerar_entradas")

    if gerar_entradas:
        if not arquivos_entrada:
            st.warning("⚠️ Faça o upload de pelo menos um arquivo de entrada para continuar.")
        elif usar_filtro_data_entradas and data_inicial_entradas > data_final_entradas:
            st.error("Corrija o período das datas.")
        else:
            with st.spinner("Processando Notas de Entrada..."):
                chaves_processadas_entradas = set()
                cont_entradas = {'duplicatas': 0, 'sem_sku': 0, 'nomes_sem_sku': []}
                
                df_entradas = processar_arquivos(arquivos_entrada, 'Entrada', chaves_processadas_entradas, cont_entradas) if arquivos_entrada else pd.DataFrame()
                
                if not df_entradas.empty:
                    df_entradas['DataFormatada'] = pd.to_datetime(df_entradas['DataEmissaoRaw'], errors='coerce').dt.date
                    
                    if usar_filtro_data_entradas:
                        df_entradas = df_entradas[(df_entradas['DataFormatada'] >= data_inicial_entradas) & (df_entradas['DataFormatada'] <= data_final_entradas)]
                    
                    if df_entradas.empty:
                        st.warning("Nenhum produto encontrado no período selecionado.")
                    else:
                        # Para entradas, apenas somamos as quantidades por SKU
                        relatorio_entradas = df_entradas.groupby('SKU', as_index=False)['Quantidade'].sum()
                        
                        # Renomeia a coluna para ficar claro na planilha
                        relatorio_entradas = relatorio_entradas.rename(columns={'Quantidade': 'Quantidade Comprada (Entrada)'})
                        relatorio_entradas = relatorio_entradas.sort_values(by='Quantidade Comprada (Entrada)', ascending=False)
                        
                        st.success(f"✅ Sucesso! Lidas {len(chaves_processadas_entradas) - cont_entradas['sem_sku']} notas de entrada válidas.")
                        if cont_entradas['duplicatas'] > 0: st.warning(f"🔄 Ignorados {cont_entradas['duplicatas']} arquivos repetidos.")
                        if cont_entradas['sem_sku'] > 0:
                            st.error(f"⚠️ {cont_entradas['sem_sku']} arquivos sem produtos.")
                            with st.expander("👀 Ver arquivos"):
                                for arq in cont_entradas['nomes_sem_sku']: st.write(f"- {arq}")
                        
                        st.dataframe(relatorio_entradas, use_container_width=True)
                        
                        buffer_ent = io.BytesIO()
                        with pd.ExcelWriter(buffer_ent, engine='openpyxl') as writer:
                            relatorio_entradas.to_excel(writer, index=False, sheet_name='Entradas')
                        
                        st.download_button("💾 Baixar Excel (Entradas)", data=buffer_ent.getvalue(), file_name="relatorio_entradas.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_entradas")
                else:
                    st.error("❌ Nenhum dado válido encontrado.")
