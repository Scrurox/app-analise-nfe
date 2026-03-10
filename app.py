import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import zipfile
import datetime

# Configuração da página do aplicativo
st.set_page_config(page_title="Analisador de NF-e", layout="wide")

st.title("📊 Analisador de Vendas e Devoluções por SKU")
st.write("Faça o upload dos seus arquivos XML ou .ZIP. O sistema consolida os dados por SKU.")

# Inicializa variável no Session State
if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0

def limpar_uploads():
    st.session_state.upload_key += 1

def extrair_dados_xml(arquivo_lido, tipo_nota, nome_arquivo, chaves_processadas, contadores):
    dados_extraidos = []
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    
    try:
        tree = ET.parse(arquivo_lido)
        root = tree.getroot()
        
        # 1. Busca a Chave de Acesso
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
        
        # 3. Busca a Data de Emissão (Formato YYYY-MM-DD para facilitar o filtro)
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
        
        # 4. Processa os itens da nota
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            if prod is not None:
                sku_node = prod.find('nfe:cProd', ns)
                qtd_node = prod.find('nfe:qCom', ns)
                
                if sku_node is not None and qtd_node is not None:
                    sku = sku_node.text
                    quantidade = float(qtd_node.text)
                    
                    dados_extraidos.append({
                        'DataEmissaoRaw': data_emissao_str, # Guardamos a data bruta para o filtro
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

# --- INTERFACE DE UPLOAD ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📥 Notas de Venda")
    arquivos_venda = st.file_uploader("Selecione os XMLs ou um ZIP de Venda", type=['xml', 'zip'], accept_multiple_files=True, key=f"vendas_{st.session_state.upload_key}")

with col2:
    st.subheader("📤 Notas de Devolução")
    arquivos_devolucao = st.file_uploader("Selecione os XMLs ou um ZIP de Devolução", type=['xml', 'zip'], accept_multiple_files=True, key=f"devolucoes_{st.session_state.upload_key}")

# --- INTERFACE DO FILTRO DE DATA ---
st.divider()
st.subheader("📅 Filtro de Período (Opcional)")
usar_filtro_data = st.checkbox("Filtrar resultados por Data de Emissão")

data_inicial, data_final = None, None
if usar_filtro_data:
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        data_inicial = st.date_input("Data Inicial", format="DD/MM/YYYY")
    with col_d2:
        data_final = st.date_input("Data Final", format="DD/MM/YYYY")
    
    if data_inicial > data_final:
        st.error("A Data Inicial não pode ser maior que a Data Final.")

# --- BOTÕES DE AÇÃO ---
st.divider()
col_btn1, col_btn2 = st.columns([2, 8])

with col_btn1:
    st.button("🗑️ Limpar Arquivos", on_click=limpar_uploads)

with col_btn2:
    gerar = st.button("🚀 Gerar Relatório Consolidado", type="primary")

# --- PROCESSAMENTO ---
if gerar:
    if not arquivos_venda and not arquivos_devolucao:
        st.warning("⚠️ Por favor, faça o upload de pelo menos um arquivo XML ou ZIP para continuar.")
    elif usar_filtro_data and data_inicial > data_final:
        st.error("Corrija o período das datas antes de gerar o relatório.")
    else:
        with st.spinner("Extraindo dados, aplicando filtros e cruzando informações..."):
            
            chaves_processadas = set()
            contadores = {'duplicatas': 0, 'sem_sku': 0, 'nomes_sem_sku': []}
            
            df_vendas = processar_arquivos(arquivos_venda, 'Venda', chaves_processadas, contadores) if arquivos_venda else pd.DataFrame()
            df_devolucoes = processar_arquivos(arquivos_devolucao, 'Devolucao', chaves_processadas, contadores) if arquivos_devolucao else pd.DataFrame()
            
            df_total = pd.concat([df_vendas, df_devolucoes])
            
            if not df_total.empty:
                # Converte a coluna de data para o formato datetime nativo do Python (se existir)
                df_total['DataFormatada'] = pd.to_datetime(df_total['DataEmissaoRaw'], errors='coerce').dt.date
                
                # APLICA O FILTRO DE DATA SE ESTIVER HABILITADO
                if usar_filtro_data:
                    # Filtra apenas as linhas onde a data está entre a inicial e final
                    # Notas sem data lida corretamente (NaT) também são removidas se o filtro for usado
                    df_total = df_total[
                        (df_total['DataFormatada'] >= data_inicial) & 
                        (df_total['DataFormatada'] <= data_final)
                    ]
                
                if df_total.empty:
                    st.warning("Nenhum produto encontrado **dentro do período selecionado**.")
                else:
                    # Agrupa o relatório APENAS por SKU (volta ao formato original consolidado)
                    relatorio = pd.pivot_table(
                        df_total, 
                        values='Quantidade', 
                        index='SKU',  # Removemos a data daqui!
                        columns='Tipo', 
                        aggfunc='sum', 
                        fill_value=0
                    ).reset_index()
                    
                    if 'Venda' not in relatorio.columns: relatorio['Venda'] = 0
                    if 'Devolucao' not in relatorio.columns: relatorio['Devolucao'] = 0
                        
                    relatorio['Saldo Líquido'] = relatorio['Venda'] - relatorio['Devolucao']
                    relatorio = relatorio.sort_values(by='Venda', ascending=False)
                    
                    notas_unicas_validas = len(chaves_processadas) - contadores['sem_sku']
                    
                    st.success(f"✅ Processamento concluído! Notas válidas analisadas: {notas_unicas_validas}.")
                    
                    if contadores['duplicatas'] > 0:
                        st.warning(f"🔄 **Duplicidade:** Ignorados {contadores['duplicatas']} arquivos repetidos.")
                    
                    if contadores['sem_sku'] > 0:
                        st.error(f"⚠️ **Atenção:** Em {contadores['sem_sku']} arquivos não havia produtos (podem ser notas canceladas).")
                        with st.expander("👀 Ver nomes dos arquivos sem SKU"):
                            for nome_arq in contadores['nomes_sem_sku']:
                                st.write(f"- {nome_arq}")
                    
                    st.dataframe(relatorio, use_container_width=True)
                    
                    # Nome do arquivo de Excel dinâmico (com ou sem data)
                    if usar_filtro_data:
                        nome_excel = f"relatorio_SKU_{data_inicial}_a_{data_final}.xlsx"
                    else:
                        nome_excel = "relatorio_SKU_periodo_total.xlsx"
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        relatorio.to_excel(writer, index=False, sheet_name='Relatorio_SKU')
                    
                    st.download_button(
                        label="💾 Baixar Relatório em Excel",
                        data=buffer.getvalue(),
                        file_name=nome_excel,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.error("❌ Nenhum produto encontrado nos arquivos processados.")
