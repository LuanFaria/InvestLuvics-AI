import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from streamlit_option_menu import option_menu
import plotly.graph_objects as go

# Configuração da página integrada de forma personalizada
st.set_page_config(page_title="Tech Luvics - Dashboard Financeiro", layout="wide", initial_sidebar_state="expanded")

DB_NAME = 'carteira_fiis.db'

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Tabela Controle
    c.execute('''CREATE TABLE IF NOT EXISTS controle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ano INTEGER, mes INTEGER, entrada REAL, caixa REAL, clear REAL, 
        poupanca REAL, caixinha REAL, aluguel REAL, contas REAL, 
        uber_carro REAL, gastos_gerais REAL, total_gastos REAL, 
        total_saida REAL, quantidade_cotas INTEGER
    )''')
    
    # 2. Tabela Fundos Imobiliários (Nova estrutura com num_cotas)
    c.execute('''CREATE TABLE IF NOT EXISTS fundos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        segmento TEXT,
        cota_atual REAL,
        pvp REAL,
        dy REAL,
        num_cotas REAL DEFAULT 0,
        total_investido REAL DEFAULT 0
    )''')
    
    # 3. Tabela Ações (Nova estrutura com num_cotas e cota_atual)
    c.execute('''CREATE TABLE IF NOT EXISTS acoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        cota_atual REAL,
        dy REAL,
        num_cotas REAL DEFAULT 0,
        total_investido REAL DEFAULT 0
    )''')
    
    # 4. Tabela Renda Fixa
    c.execute('''CREATE TABLE IF NOT EXISTS renda_fixa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        total_investido REAL,
        dy REAL
    )''')
    
    # 5. Tabela Operações (Histórico)
    c.execute('''CREATE TABLE IF NOT EXISTS operacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        data_op DATE,
        tipo TEXT,
        quantidade REAL,
        valor_unitario REAL,
        valor_total REAL
    )''')
    
    conn.commit()
    conn.close()

# Inicializar o banco de dados
init_db()

# ---- SCRIPT DE RASPAGEM (STATUS INVEST) ----
def extrair_indicador(soup, termos_busca):
    if isinstance(termos_busca, str):
        termos_busca = [termos_busca]
        
    for termo in termos_busca:
        tags_com_title = soup.find_all(lambda t: t.has_attr('title') and termo.lower() in t['title'].lower())
        for tag in tags_com_title:
            valor_tag = tag.find('strong', class_='value') or tag.find('strong')
            if valor_tag:
                val = valor_tag.get_text(strip=True)
                if val and val != '-':
                    return val
                    
    for termo in termos_busca:
        for tag in soup.find_all(['h3', 'span', 'p', 'small', 'b', 'td', 'dt']):
            texto = tag.get_text(strip=True)
            if termo.lower() == texto.lower() or (termo.lower() in texto.lower() and len(texto) <= 20):
                parent = tag
                for _ in range(4):
                    parent = parent.parent
                    if not parent: break
                    valor_tag = parent.find('strong', class_='value') or parent.find('strong')
                    if valor_tag:
                        val = valor_tag.get_text(strip=True)
                        if val and val != '-':
                            return val
    return None

def atualizar_cotacoes():
    conn = get_connection()
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://statusinvest.com.br/'
    })

    atualizados_total = 0

    # 1. Atualizar FIIs
    try:
        fundos_df = pd.read_sql("SELECT ticker FROM fundos", conn)
        for _, row in fundos_df.iterrows():
            fii = str(row['ticker']).strip().upper()
            url = f'https://statusinvest.com.br/fundos-imobiliarios/{fii.lower()}'
            try:
                response = session.get(url, timeout=12)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    val_txt = extrair_indicador(soup, ['valor atual', 'valor atual do ativo'])
                    pvp_txt = extrair_indicador(soup, ['p/vp', 'pvp'])
                    dy_txt = extrair_indicador(soup, ['dividend yield', 'dy'])

                    val_clean = float(val_txt.replace('R$', '').replace('\xa0', '').replace('.', '').replace(',', '.').strip()) if val_txt else 0.0
                    pvp_clean = float(pvp_txt.replace(',', '.').strip()) if pvp_txt else 0.0
                    dy_clean = float(dy_txt.replace(',', '.').replace('%', '').strip()) if dy_txt else 0.0

                    if val_clean > 0:
                        conn.execute("UPDATE fundos SET cota_atual = ?, pvp = ?, dy = ? WHERE ticker = ?", (val_clean, pvp_clean, dy_clean, fii))
                        atualizados_total += 1
            except:
                pass
    except Exception as e:
        pass

    # 2. Atualizar Ações
    try:
        acoes_df = pd.read_sql("SELECT ticker FROM acoes", conn)
        for _, row in acoes_df.iterrows():
            acao = str(row['ticker']).strip().upper()
            url = f'https://statusinvest.com.br/acoes/{acao.lower()}'
            try:
                response = session.get(url, timeout=12)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    val_txt = extrair_indicador(soup, ['valor atual', 'valor atual do ativo'])
                    dy_txt = extrair_indicador(soup, ['dividend yield', 'dy'])

                    val_clean = float(val_txt.replace('R$', '').replace('\xa0', '').replace('.', '').replace(',', '.').strip()) if val_txt else 0.0
                    dy_clean = float(dy_txt.replace(',', '.').replace('%', '').strip()) if dy_txt else 0.0

                    if val_clean > 0:
                        # Agora atualizamos também a cota_atual para ações
                        conn.execute("UPDATE acoes SET cota_atual = ?, dy = ? WHERE ticker = ?", (val_clean, dy_clean, acao))
                        atualizados_total += 1
            except:
                pass
    except Exception as e:
        pass

    conn.commit()
    conn.close()
    
    if atualizados_total > 0:
        st.success(f"Sucesso! {atualizados_total} ativos (FIIs e Ações) atualizados no banco de dados.")
    else:
        st.warning("⚠️ Nenhum ativo foi atualizado. Verifique se os tickers estão corretos ou tente novamente mais tarde.")

# ---- MENU LATERAL TECNOLÓGICO ----
with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: #4DA8DA; letter-spacing: 2px;'>TECH LUVICS</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #888; margin-top: -10px;'>Painel de Investimentos</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    menu = option_menu(
        menu_title=None, 
        options=["Dashboard", "Controle Mensal", "Tabelas & Carteira", "Cadastro e Operações", "Calculadora de Juros", "IA Recomendações"],
        icons=["bar-chart-fill", "wallet", "table", "arrow-left-right", "calculator", "robot"],
        menu_icon="cast", 
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#4DA8DA", "font-size": "18px"}, 
            "nav-link": {
                "font-size": "15px", 
                "text-align": "left", 
                "margin": "5px 0px", 
                "border-radius": "8px",
                "--hover-color": "transparent"
            },
            "nav-link-selected": {
                "background-color": "#1f77b4", 
                "color": "white", 
                "font-weight": "bold"
            },
        }
    )

# --- FUNÇÃO DE TRATAMENTO DE NÚMEROS (ELIMINA NaN E ERROS DO PYARROW) ---
def para_float(val):
    if pd.isna(val) or val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).replace('R$', '').replace(' ', '').strip()
    if '.' in val_str and ',' in val_str:
        val_str = val_str.replace('.', '').replace(',', '.')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
    try:
        return float(val_str)
    except:
        return 0.0

NOMES_MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

if menu == "Dashboard":
    st.title("📊 Visão Geral da Carteira")
    
    hoje = datetime.now()
    conn = get_connection()
    
    try:
        controle_df = pd.read_sql("SELECT * FROM controle ORDER BY CAST(ano AS INTEGER) DESC, CAST(mes AS INTEGER) DESC", conn)
        fundos_df = pd.read_sql("SELECT *, (num_cotas * cota_atual) AS valor_mercado FROM fundos", conn)
        acoes_df = pd.read_sql("SELECT *, (num_cotas * cota_atual) AS valor_mercado FROM acoes", conn)
        fixa_df = pd.read_sql("SELECT * FROM renda_fixa", conn)
    except Exception as e:
        st.error(f"Erro ao consultar o banco de dados: {e}")
        controle_df = fundos_df = acoes_df = fixa_df = pd.DataFrame()
    finally:
        conn.close()

    # --- SANITIZAÇÃO RIGOROSA DOS DADOS ---
    if not controle_df.empty:
        for col in controle_df.columns:
            if col.lower() in ['caixa', 'entradas', 'entrada', 'saidas', 'saida', 'saldo', 'despesas', 'receitas']:
                controle_df[col] = controle_df[col].apply(para_float)
                controle_df[col] = pd.to_numeric(controle_df[col], errors='coerce').fillna(0.0)

    if not fundos_df.empty and 'valor_mercado' in fundos_df.columns:
        fundos_df['valor_mercado'] = pd.to_numeric(fundos_df['valor_mercado'].apply(para_float), errors='coerce').fillna(0.0)
    
    if not acoes_df.empty and 'valor_mercado' in acoes_df.columns:
        acoes_df['valor_mercado'] = pd.to_numeric(acoes_df['valor_mercado'].apply(para_float), errors='coerce').fillna(0.0)

    if not fixa_df.empty and 'total_investido' in fixa_df.columns:
        fixa_df['total_investido'] = pd.to_numeric(fixa_df['total_investido'].apply(para_float), errors='coerce').fillna(0.0)

    # --- CÁLCULO DOS TOTAIS PRINCIPAIS ---
    caixa_atual = float(controle_df['caixa'].iloc[0]) if not controle_df.empty and 'caixa' in controle_df.columns else 0.0
    tot_fundos = float(fundos_df['valor_mercado'].sum()) if not fundos_df.empty and 'valor_mercado' in fundos_df.columns else 0.0
    tot_acoes = float(acoes_df['valor_mercado'].sum()) if not acoes_df.empty and 'valor_mercado' in acoes_df.columns else 0.0
    tot_fixa = float(fixa_df['total_investido'].sum()) if not fixa_df.empty and 'total_investido' in fixa_df.columns else 0.0

    # --- CARDS PRINCIPAIS (PATRIMÔNIO ATUAL) ---
    st.markdown("### Resumo do Patrimônio")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Caixa Atual", f"R$ {caixa_atual:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    m2.metric("Total FIIs", f"R$ {tot_fundos:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    m3.metric("Total Ações", f"R$ {tot_acoes:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    m4.metric("Total Renda Fixa", f"R$ {tot_fixa:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

    st.markdown("---")

    # --- GRÁFICO DE PIZZA DA CARTEIRA ---
    st.markdown("### Composição da Carteira")
    tipo_grafico = st.selectbox("Selecione o filtro do Gráfico de Pizza:", 
                                ["Divisão da Carteira", "Por Fundos", "Por Tipo de Fundo", "Ações", "Renda Fixa"])
    
    fig = None
    if tipo_grafico == "Divisão da Carteira":
        df_plot = pd.DataFrame({
            'Categoria': ['Caixa', 'FIIs', 'Ações', 'Renda Fixa'],
            'Valor': [caixa_atual, tot_fundos, tot_acoes, tot_fixa]
        })
        df_plot = df_plot[df_plot['Valor'] > 0]
        if not df_plot.empty:
            fig = px.pie(df_plot, names='Categoria', values='Valor', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            
    elif tipo_grafico == "Por Fundos" and not fundos_df.empty:
        fundos_ativos = fundos_df[fundos_df['valor_mercado'] > 0]
        if not fundos_ativos.empty:
            fig = px.pie(fundos_ativos, names='ticker', values='valor_mercado', hole=0.4)
            
    elif tipo_grafico == "Por Tipo de Fundo" and not fundos_df.empty:
        df_grp = fundos_df.groupby('segmento', as_index=False)['valor_mercado'].sum()
        df_grp = df_grp[df_grp['valor_mercado'] > 0]
        if not df_grp.empty:
            fig = px.pie(df_grp, names='segmento', values='valor_mercado', hole=0.4)
            
    elif tipo_grafico == "Ações" and not acoes_df.empty:
        acoes_ativas = acoes_df[acoes_df['valor_mercado'] > 0]
        if not acoes_ativas.empty:
            fig = px.pie(acoes_ativas, names='ticker', values='valor_mercado', hole=0.4)
            
    elif tipo_grafico == "Renda Fixa" and not fixa_df.empty:
        fixa_ativas = fixa_df[fixa_df['total_investido'] > 0]
        if not fixa_ativas.empty:
            fig = px.pie(fixa_ativas, names='ticker', values='total_investido', hole=0.4)
        
    if fig:
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Sem dados para gerar o gráfico selecionado.")

    st.markdown("---")

    # --- EXPANDER: INSPEÇÃO E FILTRO DA TABELA DE CONTROLE MENSAL ---
    with st.expander("🔍 Inspecionar Registros da Tabela de Controle Mensal"):
        if not controle_df.empty:
            st.markdown("#### 🛠️ Filtros de Análise de Gastos e Médias")
            
            col_f1, col_f2 = st.columns([1, 2])
            
            anos_disponiveis = sorted(controle_df['ano'].unique(), reverse=True)
            with col_f1:
                ano_filtro = st.selectbox("Ano", options=anos_disponiveis, index=0)
            
            df_ano = controle_df[controle_df['ano'] == ano_filtro].copy()
            meses_disponiveis = sorted(df_ano['mes'].unique())
            
            with col_f2:
                meses_filtro = st.multiselect(
                    "Selecione o(s) Mês(es) para Analisar (Ex: últimos 3 meses)",
                    options=meses_disponiveis,
                    default=meses_disponiveis,
                    format_func=lambda x: f"{x} - {NOMES_MESES.get(int(x), str(x))}"
                )
            
            # Aplica os filtros selecionados
            if meses_filtro:
                df_filtrado = df_ano[df_ano['mes'].isin(meses_filtro)].copy()
            else:
                df_filtrado = df_ano.copy()

            # Mapeamento dinâmico de colunas
            col_saidas = next((c for c in ['saidas', 'saida', 'despesas'] if c in df_filtrado.columns), None)
            col_entradas = next((c for c in ['entradas', 'entrada', 'receitas'] if c in df_filtrado.columns), None)
            col_saldo = next((c for c in ['saldo'] if c in df_filtrado.columns), None)

            num_meses_sel = len(meses_filtro) if meses_filtro else len(meses_disponiveis)
            total_gastos = df_filtrado[col_saidas].sum() if col_saidas else 0.0
            media_gastos = total_gastos / num_meses_sel if num_meses_sel > 0 else 0.0
            total_investido_entradas = df_filtrado[col_entradas].sum() if col_entradas else 0.0
            saldo_periodo = df_filtrado[col_saldo].sum() if col_saldo else (total_investido_entradas - total_gastos)

            # Métricas consolidadas dentro da aba
            st.markdown("##### 📊 Resumo do Período Selecionado")
            f_m1, f_m2, f_m3, f_m4 = st.columns(4)
            f_m1.metric("Gasto Médio Mensal", f"R$ {media_gastos:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
            f_m2.metric("Total Gasto (Saídas)", f"R$ {total_gastos:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
            f_m3.metric("Total Entradas / Receitas", f"R$ {total_investido_entradas:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
            f_m4.metric("Saldo do Período", f"R$ {saldo_periodo:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

            st.markdown("##### 📋 Registros Filtrados")
            st.dataframe(df_filtrado, width="stretch")
        else:
            st.write("A tabela de controle está vazia.")

# ==============================================================================
# 📝 MENU 2: CONTROLE MENSAL
# ==============================================================================
elif menu == "Controle Mensal":
    st.title("📝 Lançamento de Controle Mensal")
    
    hoje = datetime.now()
    
    with st.form("form_controle"):
        col1, col2 = st.columns(2)
        with col1:
            mes = st.number_input("Mês", min_value=1, max_value=12, value=int(hoje.month))
            caixa = st.number_input("Saldo Caixa Final (R$)", value=0.0, step=100.0)
            entradas = st.number_input("Entradas / Receitas do Mês (R$)", value=0.0, step=100.0)
        with col2:
            ano = st.number_input("Ano", min_value=2000, max_value=2100, value=int(hoje.year))
            saidas = st.number_input("Saídas / Gastos do Mês (R$)", value=0.0, step=100.0)
            observacao = st.text_input("Observação", value="")
            
        saldo = entradas - saidas
        st.info(f"💡 **Saldo Calculado do Mês (Entradas - Saídas):** R$ {saldo:,.2f}")
        
        btn_salvar = st.form_submit_button("💾 Salvar Mês")
        
        if btn_salvar:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Verifica se já existe o mês/ano gravado
            cursor.execute("SELECT id FROM controle WHERE ano = ? AND mes = ?", (int(ano), int(mes)))
            registro = cursor.fetchone()
            
            if registro:
                cursor.execute("""
                    UPDATE controle 
                    SET caixa = ?, entradas = ?, saidas = ?, saldo = ?, observacao = ?
                    WHERE id = ?
                """, (caixa, entradas, saidas, saldo, observacao, registro[0]))
                st.success(f"✅ Mês {mes}/{ano} atualizado com sucesso!")
            else:
                cursor.execute("""
                    INSERT INTO controle (ano, mes, caixa, entradas, saidas, saldo, observacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (int(ano), int(mes), caixa, entradas, saidas, saldo, observacao))
                st.success(f"✅ Mês {mes}/{ano} cadastrado com sucesso!")
                
            conn.commit()
            conn.close()

# ==============================================================================
# 💸 MENU 3: LANÇAR OPERAÇÕES
# ==============================================================================
elif menu == "Lançar Operações":
    st.title("💸 Cadastro e Lançamento de Operações")
    
    tipo_ativo = st.selectbox("Selecione o Tipo de Ativo:", ["FII (Fundo Imobiliário)", "Ação", "Renda Fixa"])
    
    if tipo_ativo == "FII (Fundo Imobiliário)":
        st.subheader("Lançar Operação em FII")
        with st.form("form_fii"):
            ticker = st.text_input("Ticker do FII (Ex: HGLG11)").upper().strip()
            segmento = st.text_input("Segmento (Ex: Logística, Shopping, Papel)", value="Geral")
            num_cotas = st.number_input("Quantidade de Cotas", min_value=0.0, value=0.0, step=1.0)
            cota_atual = st.number_input("Cotação Atual (R$)", min_value=0.0, value=0.0, step=0.1)
            preco_medio = st.number_input("Preço Médio (R$)", min_value=0.0, value=0.0, step=0.1)
            
            btn_fii = st.form_submit_button("Salvar FII")
            if btn_fii and ticker:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO fundos (ticker, segmento, num_cotas, cota_atual, preco_medio)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                    segmento=excluded.segmento,
                    num_cotas=excluded.num_cotas,
                    cota_atual=excluded.cota_atual,
                    preco_medio=excluded.preco_medio
                """, (ticker, segmento, num_cotas, cota_atual, preco_medio))
                conn.commit()
                conn.close()
                st.success(f"✅ FII {ticker} salvo com sucesso!")

    elif tipo_ativo == "Ação":
        st.subheader("Lançar Operação em Ação")
        with st.form("form_acao"):
            ticker = st.text_input("Ticker da Ação (Ex: PETR4)").upper().strip()
            setor = st.text_input("Setor (Ex: Bancos, Energia)", value="Geral")
            num_cotas = st.number_input("Quantidade de Cotas", min_value=0.0, value=0.0, step=1.0)
            cota_atual = st.number_input("Cotação Atual (R$)", min_value=0.0, value=0.0, step=0.1)
            preco_medio = st.number_input("Preço Médio (R$)", min_value=0.0, value=0.0, step=0.1)
            
            btn_acao = st.form_submit_button("Salvar Ação")
            if btn_acao and ticker:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO acoes (ticker, setor, num_cotas, cota_atual, preco_medio)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                    setor=excluded.setor,
                    num_cotas=excluded.num_cotas,
                    cota_atual=excluded.cota_atual,
                    preco_medio=excluded.preco_medio
                """, (ticker, setor, num_cotas, cota_atual, preco_medio))
                conn.commit()
                conn.close()
                st.success(f"✅ Ação {ticker} salva com sucesso!")

    elif tipo_ativo == "Renda Fixa":
        st.subheader("Lançar Renda Fixa")
        with st.form("form_fixa"):
            ticker = st.text_input("Nome/Descrição (Ex: Tesouro Selic 2029, CDB Inter)").strip()
            tipo = st.selectbox("Tipo", ["Tesouro Direto", "CDB", "LCI/LCA", "Cri/Cra", "Outros"])
            total_investido = st.number_input("Total Investido (R$)", min_value=0.0, value=0.0, step=100.0)
            rentabilidade = st.text_input("Rentabilidade (Ex: 100% CDI, IPCA + 6%)", value="100% CDI")
            
            btn_fixa = st.form_submit_button("Salvar Renda Fixa")
            if btn_fixa and ticker:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO renda_fixa (ticker, tipo, total_investido, rentabilidade)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                    tipo=excluded.tipo,
                    total_investido=excluded.total_investido,
                    rentabilidade=excluded.rentabilidade
                """, (ticker, tipo, total_investido, rentabilidade))
                conn.commit()
                conn.close()
                st.success(f"✅ Renda Fixa {ticker} salva com sucesso!")

# ---- TABELAS / CARTEIRA ----
elif menu == "Tabelas & Carteira":
    st.title("💼 Carteira de Investimentos")
    conn = get_connection()
    
    st.subheader("1. FIIs")
    if st.button("🔄 Atualizar Cotações (StatusInvest)"):
        with st.spinner("Buscando indicadores online..."):
            atualizar_cotacoes()
            
    try:
        df_fundos = pd.read_sql("SELECT * FROM fundos", conn)
        # Calcula a coluna de valor de mercado apenas para visualização
        if 'num_cotas' in df_fundos.columns and 'cota_atual' in df_fundos.columns:
            df_fundos.insert(loc=3, column='Valor de Mercado (R$)', value=(df_fundos['num_cotas'] * df_fundos['cota_atual']))
        st.dataframe(df_fundos, use_container_width=True)
    except: st.warning("Tabela 'fundos' não encontrada ou vazia.")
    
    st.subheader("2. Ações")
    try:
        df_acoes = pd.read_sql("SELECT * FROM acoes", conn)
        if 'num_cotas' in df_acoes.columns and 'cota_atual' in df_acoes.columns:
            df_acoes.insert(loc=3, column='Valor de Mercado (R$)', value=(df_acoes['num_cotas'] * df_acoes['cota_atual']))
        st.dataframe(df_acoes, use_container_width=True)
    except: st.warning("Tabela 'acoes' não encontrada ou vazia.")
    
    st.subheader("3. Renda Fixa")
    try:
        df_fixa = pd.read_sql("SELECT * FROM renda_fixa", conn)
        st.dataframe(df_fixa, use_container_width=True)
    except: st.warning("Tabela 'renda_fixa' não encontrada ou vazia.")
    
    conn.close()

# ---- CADASTRO E OPERAÇÕES ----
elif menu == "Cadastro e Operações":
    st.title("➕ Cadastro e Operações")
    
    tab1, tab2 = st.tabs(["Adicionar Novo Ativo", "Lançar Operação (Compra/Venda)"])
    conn = get_connection()
    c = conn.cursor()
    
    with tab1:
        tipo_ativo_novo = st.selectbox("Selecione a Categoria para Cadastro", ["FIIs", "Ações", "Renda Fixa"], key="cat_novo")
        with st.form("form_novo"):
            nome = st.text_input("Ticker ou Nome do Ativo").upper()
            
            if tipo_ativo_novo == "FIIs":
                tipo_fundo = st.selectbox("Tipo", ["Titulos Mob.", "Hibrido", "Shopping", "Laje", "Galpão Logistico", "Ação", "Outro"])
            else:
                tipo_fundo = ""
                
            if st.form_submit_button("Cadastrar Ativo", use_container_width=True):
                if nome:
                    try:
                        ticker_limpo = nome.upper().strip()
                        if tipo_ativo_novo == "FIIs":
                            conn.execute(
                                "INSERT INTO fundos (ticker, segmento, num_cotas, total_investido, cota_atual, pvp, dy) VALUES (?, ?, 0, 0, 0, 0, 0)", 
                                (ticker_limpo, tipo_fundo)
                            )
                        elif tipo_ativo_novo == "Ações":
                            conn.execute(
                                "INSERT INTO acoes (ticker, num_cotas, total_investido, cota_atual, dy) VALUES (?, 0, 0, 0, 0)", 
                                (ticker_limpo,)
                            )
                        else:
                            conn.execute(
                                "INSERT INTO renda_fixa (ticker, total_investido, dy) VALUES (?, 0, 0)", 
                                (ticker_limpo,)
                            )
                        conn.commit()
                        st.success(f"Ativo {ticker_limpo} cadastrado com sucesso nas tabelas de controle!")
                    except sqlite3.IntegrityError:
                        st.error("Este ativo já existe na base de dados.")
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

    with tab2:
        tipo_ativo_op = st.selectbox("Selecione a Categoria para Operar", ["FIIs", "Ações", "Renda Fixa"], key="cat_op")
        tabela = "fundos" if tipo_ativo_op == "FIIs" else ("acoes" if tipo_ativo_op == "Ações" else "renda_fixa")
        
        try:
            df_ativos = pd.read_sql(f"SELECT ticker FROM {tabela}", conn)
        except Exception as e:
            st.error(f"Tabela {tabela} não encontrada. Detalhes: {e}")
            df_ativos = pd.DataFrame(columns=['ticker'])
            
        if df_ativos.empty:
            st.warning("Nenhum ativo cadastrado nesta categoria. Adicione ativos na aba ao lado primeiro.")
        else:
            with st.form("form_op"):
                ativo_selecionado = st.selectbox("Ativo", df_ativos['ticker'].tolist())
                tipo_op = st.selectbox("Tipo de Ordem", ["Compra", "Venda"])
                data_op = st.date_input("Data")
                
                # MÁGICA: O Form muda se for Cota (Ação/FII) ou Dinheiro (Renda Fixa)
                if tipo_ativo_op in ["FIIs", "Ações"]:
                    qtd = st.number_input("Quantidade de Cotas", min_value=0.01, step=1.0)
                    st.info(f"Ao salvar, o sistema usará a cotação atual do banco para estimar o valor financeiro da operação no histórico.")
                else:
                    val_total = st.number_input("Valor Transacionado (R$)", min_value=1.0, step=100.0)
                    qtd = 1 # Para Renda Fixa
                    
                if st.form_submit_button("Salvar Operação", use_container_width=True):
                    multiplicador = 1 if tipo_op == "Compra" else -1
                    
                    try:
                        if tipo_ativo_op in ["FIIs", "Ações"]:
                            # Busca a cotação no banco para calcular a operação automaticamente
                            c.execute(f"SELECT cota_atual FROM {tabela} WHERE ticker = ?", (ativo_selecionado,))
                            resultado = c.fetchone()
                            cota_atual_bd = float(resultado[0]) if resultado and resultado[0] else 0.0
                            
                            val_operacao = qtd * cota_atual_bd
                            qtd_ajuste = qtd * multiplicador
                            
                            # Atualiza SÓ o número de cotas (O Dashboard cuidará de calcular o financeiro)
                            conn.execute(f"UPDATE {tabela} SET num_cotas = num_cotas + ? WHERE ticker = ?", (qtd_ajuste, ativo_selecionado))
                            
                            # Grava o histórico
                            conn.execute("""
                                INSERT INTO operacoes (ticker, data_op, tipo, quantidade, valor_unitario, valor_total) 
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (ativo_selecionado, data_op.strftime('%Y-%m-%d'), tipo_op, qtd, cota_atual_bd, val_operacao))
                        
                        else:
                            # Comportamento antigo mantido para Renda Fixa
                            valor_ajuste = val_total * multiplicador
                            conn.execute("UPDATE renda_fixa SET total_investido = total_investido + ? WHERE ticker = ?", (valor_ajuste, ativo_selecionado))
                            
                            conn.execute("""
                                INSERT INTO operacoes (ticker, data_op, tipo, quantidade, valor_unitario, valor_total) 
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (ativo_selecionado, data_op.strftime('%Y-%m-%d'), tipo_op, 1, val_total, val_total))
                            
                        conn.commit()
                        st.success("Operação realizada! Posição de cotas atualizada no patrimônio.")
                    except Exception as e:
                        st.error(f"Erro ao registrar a operação: {e}")
                        
    conn.close()

# ---- CALCULADORA ----
elif menu == "Calculadora de Juros":
    st.title("🧮 Calculadora de Juros Compostos")
    st.markdown("Faça projeções rápidas do seu crescimento patrimonial.")
    
    col1, col2 = st.columns(2)
    with col1:
        cap_inicial = st.number_input("Investimento Inicial (R$)", value=1000.0)
        aporte = st.number_input("Aporte Mensal (R$)", value=300.0)
    with col2:
        taxa = st.number_input("Rentabilidade Mensal Esperada (%)", value=0.85)
        meses = st.number_input("Período (Meses)", value=120)
        
    if st.button("Simular Crescimento", use_container_width=True):
        saldo = cap_inicial
        hist = []
        for m in range(1, meses + 1):
            saldo = saldo * (1 + taxa / 100) + aporte
            hist.append({"Mês": m, "Saldo": saldo})
            
        df_simulacao = pd.DataFrame(hist)
        st.metric("Estimativa de Patrimônio Final", f"R$ {saldo:,.2f}")
        fig = px.line(df_simulacao, x="Mês", y="Saldo", title="Projeção do Patrimônio no Tempo")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

# ---- IA RECOMENDAÇÕES ----
elif menu == "IA Recomendações":
    st.title("🤖 Análise de Carteira com IA")
    st.info("Em breve: o algoritmo analisará seu banco 'carteira_fiis.db', processará os indicadores atualizados de P/VP e Dividend Yield, e fornecerá inputs para equilibrar a carteira seguindo sua estratégia na Tech Luvics.")
