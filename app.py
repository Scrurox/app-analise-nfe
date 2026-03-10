import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io
import zipfile

# Configuração da página do aplicativo
st.set_page_config(page_title="Analisador de NF-e", layout="wide")

st.title("📊 Analisador de Vendas e Devoluções por SKU")
st.write("Faça o upload dos seus arquivos XML ou .ZIP. O sistema consolida os dados, ignora duplicatas e alerta sobre arquivos inválidos.")

# Inicializa uma variável de controle no Session State para limpar os arquivos
if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0

def limpar_uploads():
    st.session_state.upload_key += 1

# Função auxiliar para extrair os dados e popular os contadores
def extrair_dados_xml(arquivo_lido, tipo_nota, nome_arquivo, chaves_processadas, contadores):
    dados_extraidos = []
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    
    try:
        tree = ET.parse(arquivo_lido)
        root = tree.getroot()
        
        # Busca a Chave de Acesso da nota
        inf_nfe = root.find('.//nfe:infNFe', ns)
        
        if inf_nfe is not None and 'Id' in inf_nfe.attrib:
            chave_acesso = inf_nfe.attrib['Id']
        else:
            chave_acesso = nome_arquivo
            
        # Verifica se a nota já foi processada (Duplicidade)
        if chave_acesso in chaves_processadas:
            contadores['duplicatas'] += 1
            return [] 
            
        chaves_processadas.add(chave_acesso)
        
        # Processa os itens da nota
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            if prod is not None:
                sku_node = prod.find('nfe:cProd', ns)
                qtd_node = prod.find('nfe:qCom', ns)
                
                # Garante que as tags existem antes de tentar ler
                if sku_node is not None and qtd_node is not None:
                    sku = sku_node.text
                    quantidade = float(qtd_node.text)
                    
                    dados_extraidos.append({
                        'SKU': sku,
                        'Quantidade': quantidade,
                        'Tipo': tipo_nota
                    })
        
        # Se após ler o XML nenhum produto foi encontrado, registra o aviso
        if len(dados_extraidos) == 0:
            contadores['sem_sku'] += 1
            contadores['nomes_sem_sku'].append(nome_arquivo)
            
    except Exception as e:
        if not nome_arquivo.startswith('__MACOSX') and not nome_arquivo.startswith('.'):
            st.error(f"Erro ao ler o arquivo {nome_arquivo}: {e}")
            
    return dados_extraidos

# Função principal de processamento
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

# Criando duas colunas no aplicativo para os uploads
col1, col2 = st.columns(2)

with col1:
    st.subheader("📥 Notas de Venda")
    arquivos_venda = st.file_uploader(
        "Selecione os XMLs ou um ZIP de Venda", 
        type=['xml', 'zip'], 
        accept_multiple_files=True, 
        key=f"vendas_{st.session_state.upload_key}"
    )

with col2:
    st.subheader("📤 Notas de Devolução")
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
        with st.spinner("Analisando notas, cruzando dados e verificando inconsistências..."):
            
            # Controles Globais
            chaves_processadas = set()
            contadores = {
                'duplicatas': 0, 
                'sem_sku': 0, 
                'nomes_sem_sku': []
            }
            
            df_vendas = processar_arquivos(arquivos_venda, 'Venda', chaves_processadas, contadores) if arquivos_venda else pd.DataFrame()
            df_devolucoes = processar_arquivos(arquivos_devolucao, 'Devolucao', chaves_processadas, contadores) if arquivos_devolucao else pd.DataFrame()
            
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
                
                notas_unicas_validas = len(chaves_processadas) - contadores['sem_sku']
                
                # --- EXIBIÇÃO DOS RESULTADOS E AVISOS ---
                st.success(f"✅ Processamento concluído! Foram lidos itens de {notas_unicas_validas} notas fiscais válidas.")
                
                # Aviso de Duplicatas
                if contadores['duplicatas'] > 0:
                    st.warning(f"🔄 **Duplicidade:** Foram detectados e ignorados **{contadores['duplicatas']} arquivos repetidos**.")
                
                # Aviso de Notas Sem SKU
                if contadores['sem_sku'] > 0:
                    st.error(f"⚠️ **Atenção:** Em **{contadores['sem_sku']} arquivos únicos**, não foi possível encontrar produtos/SKUs (podem ser notas canceladas, denegadas ou cartas de correção).")
                    # Cria um menu expansível para o usuário ver os nomes dos arquivos com problema
                    with st.expander("👀 Ver nomes dos arquivos sem SKU"):
                        for nome_arq in contadores['nomes_sem_sku']:
                            st.write(f"- {nome_arq}")
                
                st.dataframe(relatorio, use_container_width=True)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    relatorio.to_excel(writer, index=False, sheet_name='Relatorio_SKU')
                
                st.download_button(
                    label="💾 Baixar Relatório em Excel",
                    data=buffer.getvalue(),
                    file_name="relatorio_vendas_devolucoes_final.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("❌ Nenhum produto encontrado nos arquivos processados.")
                # Se tudo o que o usuário subiu for arquivo de erro/evento, avisa ele do porquê
                if contadores['sem_sku'] > 0:
                    st.info(f"O sistema encontrou {contadores['sem_sku']} arquivos, mas nenhum deles possuía SKUs.")
