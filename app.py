import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io

# Configuração da página do aplicativo
st.set_page_config(page_title="Analisador de NF-e", layout="wide")

st.title("📊 Analisador de Vendas e Devoluções por SKU")
st.write("Faça o upload dos seus arquivos XML de Venda e de Devolução para gerar o relatório consolidado.")

# Inicializa uma variável de controle no Session State para limpar os arquivos
if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0

# Função para resetar os uploads
def limpar_uploads():
    st.session_state.upload_key += 1

# Função para processar os XMLs e extrair os dados
def processar_xmls(lista_arquivos, tipo_nota):
    dados = []
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
    
    for arquivo in lista_arquivos:
        try:
            # Lendo o arquivo que foi feito upload
            tree = ET.parse(arquivo)
            root = tree.getroot()
            
            for det in root.findall('.//nfe:det', ns):
                prod = det.find('nfe:prod', ns)
                
                if prod is not None:
                    sku = prod.find('nfe:cProd', ns).text
                    quantidade = float(prod.find('nfe:qCom', ns).text)
                    
                    dados.append({
                        'SKU': sku,
                        'Quantidade': quantidade,
                        'Tipo': tipo_nota
                    })
        except Exception as e:
            st.error(f"Erro ao ler o arquivo {arquivo.name}: {e}")
            
    return pd.DataFrame(dados)

# Criando duas colunas no aplicativo para os uploads
col1, col2 = st.columns(2)

with col1:
    st.subheader("📥 Notas de Venda")
    # A chave agora usa a variável do session_state
    arquivos_venda = st.file_uploader(
        "Selecione os XMLs de Venda", 
        type=['xml'], 
        accept_multiple_files=True, 
        key=f"vendas_{st.session_state.upload_key}"
    )

with col2:
    st.subheader("📤 Notas de Devolução")
    # A chave agora usa a variável do session_state
    arquivos_devolucao = st.file_uploader(
        "Selecione os XMLs de Devolução", 
        type=['xml'], 
        accept_multiple_files=True, 
        key=f"devolucoes_{st.session_state.upload_key}"
    )

# Linha divisória e botões de ação
st.divider()
col_btn1, col_btn2 = st.columns([2, 8])

with col_btn1:
    # Botão para limpar os arquivos
    st.button("🗑️ Limpar Arquivos", on_click=limpar_uploads)

with col_btn2:
    # Botão para gerar o relatório
    gerar = st.button("🚀 Gerar Relatório Consolidado", type="primary")

if gerar:
    if not arquivos_venda and not arquivos_devolucao:
        st.warning("⚠️ Por favor, faça o upload de pelo menos um arquivo XML para continuar.")
    else:
        with st.spinner("Processando arquivos..."):
            
            # Processa as vendas e devoluções
            df_vendas = processar_xmls(arquivos_venda, 'Venda') if arquivos_venda else pd.DataFrame()
            df_devolucoes = processar_xmls(arquivos_devolucao, 'Devolucao') if arquivos_devolucao else pd.DataFrame()
            
            # Junta tudo em uma única tabela
            df_total = pd.concat([df_vendas, df_devolucoes])
            
            if not df_total.empty:
                # Cria uma tabela dinâmica separando Vendas e Devoluções
                relatorio = pd.pivot_table(
                    df_total, 
                    values='Quantidade', 
                    index='SKU', 
                    columns='Tipo', 
                    aggfunc='sum', 
                    fill_value=0
                ).reset_index()
                
                # Garante que as colunas existam
                if 'Venda' not in relatorio.columns:
                    relatorio['Venda'] = 0
                if 'Devolucao' not in relatorio.columns:
                    relatorio['Devolucao'] = 0
                    
                # Calcula o saldo líquido
                relatorio['Saldo Líquido'] = relatorio['Venda'] - relatorio['Devolucao']
                
                # Ordena pelo que mais vendeu
                relatorio = relatorio.sort_values(by='Venda', ascending=False)
                
                st.success("✅ Relatório gerado com sucesso!")
                
                # Mostra a tabela na tela do app
                st.dataframe(relatorio, use_container_width=True)
                
                # Prepara o arquivo Excel para download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    relatorio.to_excel(writer, index=False, sheet_name='Relatorio_SKU')
                
                # Botão de Download do Excel
                st.download_button(
                    label="💾 Baixar Relatório em Excel",
                    data=buffer.getvalue(),
                    file_name="relatorio_vendas_devolucoes.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("❌ Nenhum produto encontrado nos arquivos XML. Verifique se os arquivos são válidos.")
