
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from streamlit_option_menu import option_menu

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
    
# 1. Tabela Fundos Imobiliários
    c.execute('''CREATE TABLE IF NOT EXISTS fundos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        segmento TEXT,
        cota_atual REAL,
        pvp REAL,
        dy REAL,
        total_investido REAL
    )''')
    
    # 2. Tabela Ações
    c.execute('''CREATE TABLE IF NOT EXISTS acoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        total_investido REAL,
        dy REAL
    )''')
    
    # 3. Tabela Renda Fixa
    c.execute('''CREATE TABLE IF NOT EXISTS renda_fixa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        total_investido REAL,
        dy REAL
    )''')
    
    # 4. Tabela Operações (Histórico)
    c.execute('''CREATE TABLE IF NOT EXISTS operacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        data_op DATE,
        tipo TEXT,
        quantidade INTEGER,
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

def buscar_indicadores(fii):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://statusinvest.com.br/'
    })
    url = f'https://statusinvest.com.br/fundos-imobiliarios/{fii.lower()}'
    try:
        response = session.get(url, timeout=12)
        if response.status_code != 200: return None, None, None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        valor_atual_text = extrair_indicador(soup, ['valor atual', 'valor atual do ativo'])
        pvp_text = extrair_indicador(soup, ['p/vp', 'pvp'])
        dy_text = extrair_indicador(soup, ['dividend yield', 'dy'])
        
        val_clean = float(valor_atual_text.replace('R$', '').replace('.', '').replace(',', '.').strip()) if valor_atual_text else None
        pvp_clean = float(pvp_text.replace(',', '.').strip()) if pvp_text else None
        dy_clean = float(dy_text.replace(',', '.').replace('%', '').strip()) if dy_text else None
        
        return val_clean, pvp_clean, dy_clean
    except Exception:
        return None, None, None
    
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
    fundos_df = pd.read_sql("SELECT ticker FROM fundos", conn)
    print(fundos_df)
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

    # 2. Atualizar Ações
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
                    conn.execute("UPDATE acoes SET dy = ? WHERE ticker = ?", (dy_clean, acao))
                    # Nota: Se na sua tabela 'acoes' você tiver uma coluna de preço/cotação atual, pode incluir aqui também (ex: preco_atual = ?)
                    atualizados_total += 1
        except:
            pass

    conn.commit()
    conn.close()
    
    if atualizados_total > 0:
        st.success(f"Sucesso! {atualizados_total} ativos (FIIs e Ações) atualizados no banco de dados.")
    else:
        st.warning("⚠️ Nenhum ativo foi atualizado. Verifique se os tickers de ações estão corretos (ex: PETR4, VALE3).")
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
                "--hover-color": "transparent" # Remove o fundo preto/cinza do hover
            },
            "nav-link-selected": {
                "background-color": "#1f77b4", 
                "color": "white", 
                "font-weight": "bold"
            },
        }
    )

# ---- DASHBOARD ----
if menu == "Dashboard":
    st.title("📊 Visão Geral da Carteira")
    
    col_mes, col_ano = st.columns(2)
    hoje = datetime.now()
    with col_mes:
        mes_atual = st.number_input("Mês de Referência", min_value=1, max_value=12, value=hoje.month)
    with col_ano:
        ano_atual = st.number_input("Ano de Referência", min_value=2000, max_value=2100, value=hoje.year)
        
    conn = get_connection()
    try:
        controle_df = pd.read_sql(f"SELECT * FROM controle WHERE mes={mes_atual} AND ano={ano_atual}", conn)
        fundos_df = pd.read_sql("SELECT * FROM fundos", conn)
        acoes_df = pd.read_sql("SELECT * FROM acoes", conn)
        fixa_df = pd.read_sql("SELECT * FROM renda_fixa", conn)
    except Exception as e:
        st.warning(f"As tabelas ainda não foram inicializadas ou preenchidas corretamente no seu banco. Detalhes: {e}")
        controle_df = fundos_df = acoes_df = fixa_df = pd.DataFrame()
        
    conn.close()
    
    caixa_atual = controle_df['caixa'].sum() if not controle_df.empty and 'caixa' in controle_df.columns else 0.0
    tot_fundos = fundos_df['total_investido'].sum() if not fundos_df.empty and 'total_investido' in fundos_df.columns else 0.0
    tot_acoes = acoes_df['total_investido'].sum() if not acoes_df.empty and 'total_investido' in acoes_df.columns else 0.0
    tot_fixa = fixa_df['total_investido'].sum() if not fixa_df.empty and 'total_investido' in fixa_df.columns else 0.0
    
    st.markdown("### Resumo do Patrimônio")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Caixa Atual", f"R$ {caixa_atual:,.2f}")
    m2.metric("Total FIIs", f"R$ {tot_fundos:,.2f}")
    m3.metric("Total Ações", f"R$ {tot_acoes:,.2f}")
    m4.metric("Total Renda Fixa", f"R$ {tot_fixa:,.2f}")
    
    st.markdown("---")
    st.markdown("### Composição da Carteira")
    tipo_grafico = st.selectbox("Selecione o filtro do Gráfico de Pizza:", 
                                ["Divisão da Carteira", "Por Fundos", "Por Tipo de Fundo", "Ações", "Renda Fixa"])
    
    fig = None
    if tipo_grafico == "Divisão da Carteira":
        df_plot = pd.DataFrame({
            'Categoria': ['Caixa', 'FIIs', 'Ações', 'Renda Fixa'],
            'Valor': [caixa_atual, tot_fundos, tot_acoes, tot_fixa]
        })
        fig = px.pie(df_plot, names='Categoria', values='Valor', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
    elif tipo_grafico == "Por Fundos" and not fundos_df.empty:
        fig = px.pie(fundos_df, names='ticker', values='total_investido', hole=0.4)
    elif tipo_grafico == "Por Tipo de Fundo" and not fundos_df.empty:
        df_grp = fundos_df.groupby('segmento', as_index=False)['total_investido'].sum()
        fig = px.pie(df_grp, names='segmento', values='total_investido', hole=0.4)
    elif tipo_grafico == "Ações" and not acoes_df.empty:
        fig = px.pie(acoes_df, names='ticker', values='total_investido', hole=0.4)
    elif tipo_grafico == "Renda Fixa" and not fixa_df.empty:
        fig = px.pie(fixa_df, names='ticker', values='total_investido', hole=0.4)
        
    if fig:
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados disponíveis para gerar o gráfico selecionado.")

# ---- CONTROLE MENSAL (Planilha 1) ----
elif menu == "Controle Mensal":
    st.title("📝 Controle Mensal")
    with st.form("form_controle"):
        col1, col2 = st.columns(2)
        ano = col1.number_input("Ano", value=datetime.now().year, step=1)
        mes = col2.number_input("Mês", value=datetime.now().month, min_value=1, max_value=12, step=1)
        
        st.markdown("**Entradas e Caixa**")
        c1, c2 = st.columns(2)
        entrada = c1.number_input("Salário/Trabalhos (R$)", step=100.0)
        caixa = c2.number_input("Caixa Total Atual (R$ - Mercado Pago, Bradesco, etc.)", step=100.0)
        
        st.markdown("**Investimentos do Mês**")
        c3, c4, c5 = st.columns(3)
        clear = c3.number_input("Corretora Clear (R$)", step=50.0)
        poupanca = c4.number_input("Poupança (R$)", step=50.0)
        caixinha = c5.number_input("Caixinha (R$)", step=50.0)
        qtd_cotas = st.number_input("Quantidade de Cotas Compradas no Mês", step=1)
        
        st.markdown("**Gastos**")
        c6, c7, c8, c9 = st.columns(4)
        aluguel = c6.number_input("Aluguel (R$)", step=50.0)
        contas = c7.number_input("Contas (R$)", step=50.0)
        uber_carro = c8.number_input("Uber/Carro (R$)", step=50.0)
        gastos_gerais = c9.number_input("Gastos Gerais (R$)", step=50.0)
        
        if st.form_submit_button("Salvar Mês", use_container_width=True):
            tot_gastos = aluguel + contas + uber_carro + gastos_gerais
            tot_saida = tot_gastos + clear + poupanca + caixinha
            
            conn = get_connection()
            conn.execute('''
                INSERT INTO controle (ano, mes, entrada, caixa, clear, poupanca, caixinha, aluguel, contas, uber_carro, gastos_gerais, total_gastos, total_saida, quantidade_cotas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ano, mes, entrada, caixa, clear, poupanca, caixinha, aluguel, contas, uber_carro, gastos_gerais, tot_gastos, tot_saida, qtd_cotas))
            conn.commit()
            conn.close()
            st.success("Controle do mês salvo com sucesso!")

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
        st.dataframe(df_fundos, use_container_width=True)
    except: st.warning("Tabela 'fundos' não encontrada ou vazia.")
    
    st.subheader("2. Ações")
    try:
        df_acoes = pd.read_sql("SELECT * FROM acoes", conn)
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
    
    # Abas para um visual mais limpo em vez de Radio Buttons simples
    tab1, tab2 = st.tabs(["Adicionar Novo Ativo", "Lançar Operação (Compra/Venda)"])
    conn = get_connection()
    
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
                        if tipo_ativo_novo == "FIIs":
                            # Removido 'quantidade_cotas' e alterado 'nome' para 'ticker'
                            conn.execute(
                                "INSERT INTO fundos (ticker, segmento, total_investido, cota_atual, pvp, dy) VALUES (?, ?, 0, 0, 0, 0)", 
                                (nome.upper().strip(), tipo_fundo)
                            )
                        elif tipo_ativo_novo == "Ações":
                            # Alterado 'nome' para 'ticker' e inicializado 'dy' como 0
                            conn.execute(
                                "INSERT INTO acoes (ticker, total_investido, dy) VALUES (?, 0, 0)", 
                                (nome.upper().strip(),)
                            )
                        else:
                            # Alterado 'nome' para 'ticker' e inicializado 'dy' como 0
                            conn.execute(
                                "INSERT INTO renda_fixa (ticker, total_investido, dy) VALUES (?, 0, 0)", 
                                (nome.strip(),)
                            )
                        conn.commit()
                        st.success(f"Ativo {nome} cadastrado com sucesso nas tabelas de controle!")
                    except sqlite3.IntegrityError:
                        st.error("Este ativo já existe na base de dados.")
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

    with tab2:
        tipo_ativo_op = st.selectbox("Selecione a Categoria para Operar", ["FIIs", "Ações", "Renda Fixa"], key="cat_op")
        tabela = "fundos" if tipo_ativo_op == "FIIs" else ("acoes" if tipo_ativo_op == "Ações" else "renda_fixa")
        
        # Correção do Erro pd.read_sql
        try:
            df_ativos = pd.read_sql(f"SELECT ticker FROM {tabela}", conn)
        except Exception as e:
            st.error(f"Tabela {tabela} não encontrada no banco de dados. Cadastre um ativo ou verifique o banco de dados. Detalhes: {e}")
            df_ativos = pd.DataFrame(columns=['ticker'])
            
        if df_ativos.empty:
            st.warning("Nenhum ativo cadastrado nesta categoria. Adicione ativos na aba ao lado primeiro.")
        else:
            with st.form("form_op"):
                ativo_selecionado = st.selectbox("Ativo", df_ativos['ticker'].tolist())
                tipo_op = st.selectbox("Tipo de Ordem", ["Compra", "Venda"])
                data_op = st.date_input("Data")
                
                if tipo_ativo_op in ["FIIs", "Ações"]:
                    qtd = st.number_input("Quantidade", min_value=1, step=1)
                    preco = st.number_input("Preço Unitário (R$)", min_value=0.01, step=1.0)
                    val_total = qtd * preco
                else:
                    qtd = 1
                    val_total = st.number_input("Valor Transacionado (R$)", min_value=1.0, step=100.0)
                    preco = val_total
                    
                st.info(f"**Total da Operação: R$ {val_total:,.2f}**")
                
                if st.form_submit_button("Salvar Operação", use_container_width=True):
                    multiplicador = 1 if tipo_op == "Compra" else -1
                    valor_calc = val_total * multiplicador
                    
                    try:
                        # CORREÇÃO AQUI: Certifique-se de que a ordem dos valores bate com as colunas
                        # A coluna na tabela é 'ticker', não 'ativo_nome'
                        conn.execute("""
                            INSERT INTO operacoes (ticker, data_op, tipo, quantidade, valor_unitario, valor_total) 
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (ativo_selecionado, data_op.strftime('%Y-%m-%d'), tipo_op, qtd, preco, val_total))
                        
                        # Atualização do saldo do ativo
                        if tipo_ativo_op == "FIIs":
                            conn.execute("UPDATE fundos SET total_investido = total_investido + ? WHERE ticker = ?", (valor_calc, ativo_selecionado))
                        elif tipo_ativo_op == "Ações":
                            conn.execute("UPDATE acoes SET total_investido = total_investido + ? WHERE ticker = ?", (valor_calc, ativo_selecionado))
                        else:
                            conn.execute("UPDATE renda_fixa SET total_investido = total_investido + ? WHERE ticker = ?", (valor_calc, ativo_selecionado))
                            
                        conn.commit()
                        st.success("Operação realizada com sucesso. Patrimônio atualizado!")
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
