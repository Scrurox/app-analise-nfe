import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import zipfile

# Configuração da página do aplicativo
st.set_page_config(page_title="Analisador de NF-e", layout="wide")

st.title("📊 Analisador de Vendas e Devoluções por SKU")
st.write("Faça o upload dos seus arquivos XML ou .ZIP. O sistema ignora automaticamente notas fiscais duplicadas.")

# Inicializa uma variável de controle no Session State para limpar os arquivos
if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0

def limpar_uploads():
    st.session_state.upload_key += 1

# Função auxiliar para extrair os dados e checar a chave de acesso
def extrair_dados_xml(arquivo_lido, tipo_nota, nome_arquivo, chaves_processadas):
    dados_extraidos = []
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    
    try:
        tree = ET.parse(arquivo_lido)
        root = tree.getroot()
        
        # 1. Busca a tag infNFe para capturar a Chave de Acesso única da nota
        inf_nfe = root.find('.//nfe:infNFe', ns)
        
        if inf_nfe is not None and 'Id' in inf_nfe.attrib:
            chave_acesso = inf_nfe.attrib['Id'] # Ex: 'NFe35230100000000000000000000000000000000000000'
        else:
            # Fallback caso seja um XML fora do padrão, usa o nome do arquivo
            chave_acesso = nome_arquivo
            
        # 2. Verifica se a nota já foi processada nesta execução
        if chave_acesso in chaves_processadas:
            return [] # Ignora o arquivo e retorna vazio para evitar duplicidade
            
        # 3. Se é inédita, adiciona a chave na lista de controle
        chaves_processadas.add(chave_acesso)
        
        # 4. Processa os itens da nota
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            if prod is not None:
                sku = prod.find('nfe:cProd', ns).text
                quantidade = float(prod.find('nfe:qCom', ns).text)
                
                dados_extraidos.append({
                    'SKU': sku,
                    'Quantidade': quantidade,
                    'Tipo': tipo_nota
                })
    except Exception as e:
        if not nome_arquivo.startswith('__MACOSX') and not nome_arquivo.startswith('.'):
            st.error(f"Erro ao ler o arquivo {nome_arquivo}: {e}")
            
    return dados_extraidos

# Função principal de processamento
def processar_arquivos(lista_arquivos, tipo_nota, chaves_processadas):
    dados_finais = []
    
    for arquivo in lista_arquivos:
        if arquivo.name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(arquivo) as z:
                    for nome_arquivo_interno in z.namelist():
                        if nome_arquivo_interno.lower().endswith('.xml'):
                            with z.open(nome_arquivo_interno) as f:
                                dados_finais.extend(extrair_dados_xml(f, tipo_nota, nome_arquivo_interno, chaves_processadas))
            except Exception as e:
                st.error(f"Erro ao abrir o arquivo ZIP {arquivo.name}: {e}")
                
        elif arquivo.name.lower().endswith('.xml'):
            dados_finais.extend(extrair_dados_xml(arquivo, tipo_nota, arquivo.name, chaves_processadas))
            
    return pd.DataFrame(dados_finais)

# Criando duas colunas no aplicativo para os uploads
col1, col2 = st.columns(2)

with col1:
    st.subheader("📥 Notas de Venda")
    st.info("Dica: Para muitas notas, compacte em um arquivo .ZIP")
    arquivos_venda = st.file_uploader(
        "Selecione os XMLs ou um ZIP de Venda", 
        type=['xml', 'zip'], 
        accept_multiple_files=True, 
        key=f"vendas_{st.session_state.upload_key}"
    )

with col2:
    st.subheader("📤 Notas de Devolução")
    st.info("Dica: Para muitas notas, compacte em um arquivo .ZIP")
    arquivos_devolucao = st.file_uploader(
        "Selecione os XMLs ou um ZIP de Devolução", 
        type=['xml', 'zip'], 
        accept_multiple_files=True, 
        key=f"devolucoes_{st.session_state.upload_key}"
    )

st.divider()
col_btn1, col_btn2 = st.columns([2, 8])

with col_btn1:
    st.button("🗑️ Limpar Arquivos", on_click=limpar_uploads)

with col_btn2:
    gerar = st.button("🚀 Gerar Relatório Consolidado", type="primary")

if gerar:
    if not arquivos_venda and not arquivos_devolucao:
        st.warning("⚠️ Por favor, faça o upload de pelo menos um arquivo XML ou ZIP para continuar.")
    else:
        with st.spinner("Processando arquivos, identificando chaves e removendo duplicidades..."):
            
            # Conjunto global (Set) para armazenar as chaves de acesso lidas e evitar duplicidade
            chaves_processadas = set()
            
            df_vendas = processar_arquivos(arquivos_venda, 'Venda', chaves_processadas) if arquivos_venda else pd.DataFrame()
            df_devolucoes = processar_arquivos(arquivos_devolucao, 'Devolucao', chaves_processadas) if arquivos_devolucao else pd.DataFrame()
            
            df_total = pd.concat([df_vendas, df_devolucoes])
            
            if not df_total.empty:
                relatorio = pd.pivot_table(
                    df_total, 
                    values='Quantidade', 
                    index='SKU', 
                    columns='Tipo', 
                    aggfunc='sum', 
                    fill_value=0
                ).reset_index()
                
                if 'Venda' not in relatorio.columns: relatorio['Venda'] = 0
                if 'Devolucao' not in relatorio.columns: relatorio['Devolucao'] = 0
                    
                relatorio['Saldo Líquido'] = relatorio['Venda'] - relatorio['Devolucao']
                relatorio = relatorio.sort_values(by='Venda', ascending=False)
                
                notas_unicas = len(chaves_processadas)
                st.success(f"✅ Sucesso! Foram processadas {notas_unicas} notas fiscais únicas (duplicatas foram ignoradas).")
                
                st.dataframe(relatorio, use_container_width=True)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    relatorio.to_excel(writer, index=False, sheet_name='Relatorio_SKU')
                
                st.download_button(
                    label="💾 Baixar Relatório em Excel",
                    data=buffer.getvalue(),
                    file_name="relatorio_vendas_devolucoes_sem_duplicidade.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("❌ Nenhum produto encontrado. Verifique se os arquivos contêm XMLs de NF-e válidos.")
