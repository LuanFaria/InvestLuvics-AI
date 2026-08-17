import sqlite3
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_option_menu import option_menu

# Configuração da página
st.set_page_config(
    page_title="Tech Luvics - Dashboard Financeiro",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_NAME = "carteira_fiis.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # 1. Tabela Controle (Adicionado saldo_bradesco e saldo_mercado_pago)
    c.execute("""CREATE TABLE IF NOT EXISTS controle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ano INTEGER, mes INTEGER, entrada REAL DEFAULT 0, caixa REAL DEFAULT 0, clear REAL DEFAULT 0, 
        poupanca REAL DEFAULT 0, caixinha REAL DEFAULT 0, aluguel REAL DEFAULT 0, contas REAL DEFAULT 0, 
        uber_carro REAL DEFAULT 0, gastos_gerais REAL DEFAULT 0, total_gastos REAL DEFAULT 0, 
        total_saida REAL DEFAULT 0, quantidade_cotas INTEGER DEFAULT 0,
        saldo_bradesco REAL DEFAULT 0, saldo_mercado_pago REAL DEFAULT 0
    )""")

    # Tenta adicionar as colunas caso o banco já tenha sido criado antes de atualizarmos o código
    try:
        c.execute("ALTER TABLE controle ADD COLUMN saldo_bradesco REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE controle ADD COLUMN saldo_mercado_pago REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # Adicionando colunas de checks mensais na tabela controle
    checks_mensais = [
        "check_gympass", "check_energia", "check_agua", "check_aluguel",
        "check_internet", "check_telefone", "check_spotify", "check_netflix"
    ]
    for check in checks_mensais:
        try:
            c.execute(f"ALTER TABLE controle ADD COLUMN {check} INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

    # 2. Tabela Fundos Imobiliários
    c.execute("""CREATE TABLE IF NOT EXISTS fundos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        segmento TEXT,
        cota_atual REAL DEFAULT 0,
        pvp REAL DEFAULT 0,
        dy REAL DEFAULT 0,
        num_cotas REAL DEFAULT 0,
        total_investido REAL DEFAULT 0
    )""")

    # 3. Tabela Ações
    c.execute("""CREATE TABLE IF NOT EXISTS acoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        cota_atual REAL DEFAULT 0,
        dy REAL DEFAULT 0,
        num_cotas REAL DEFAULT 0,
        total_investido REAL DEFAULT 0
    )""")

    # 4. Tabela Renda Fixa
    c.execute("""CREATE TABLE IF NOT EXISTS renda_fixa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE,
        total_investido REAL DEFAULT 0,
        dy REAL DEFAULT 0
    )""")

    # 5. Tabela Operações
    c.execute("""CREATE TABLE IF NOT EXISTS operacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        data_op DATE,
        tipo TEXT,
        quantidade REAL,
        valor_unitario REAL,
        valor_total REAL
    )""")

    conn.commit()
    conn.close()

# Inicializar banco de dados
init_db()

# --- TRATAMENTO E HIGIENIZAÇÃO DE NÚMEROS ---
def para_float(val):
    if pd.isna(val) or val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).replace("R$", "").replace(" ", "").strip()
    if "." in val_str and "," in val_str:
        val_str = val_str.replace(".", "").replace(",", ".")
    elif "," in val_str:
        val_str = val_str.replace(",", ".")
    try:
        return float(val_str)
    except:
        return 0.0

def limpar_dataframe_numerico(
    df,
    cols_ignorar=[
        "id", "ano", "mes", "ticker", "segmento",
        "tipo", "data_op", "observacao",
    ],
):
    if df.empty:
        return df
    df_limpo = df.copy()
    for col in df_limpo.columns:
        if col.lower() not in cols_ignorar:
            df_limpo[col] = (
                df_limpo[col].apply(para_float).astype(float).fillna(0.0)
            )
    return df_limpo

# --- FUNÇÃO DE OBTENÇÃO DOS SALDOS DO MÊS ANTERIOR ---
def obter_saldos_mes_anterior(conn, ano, mes):
    """Busca os valores de caixa e dos bancos gravados no mês anterior."""
    cursor = conn.cursor()
    if mes == 1:
        ano_ant = ano - 1
        mes_ant = 12
    else:
        ano_ant = ano
        mes_ant = mes - 1

    cursor.execute(
        "SELECT caixa, saldo_bradesco, saldo_mercado_pago FROM controle WHERE ano = ? AND mes = ?", (ano_ant, mes_ant)
    )
    res = cursor.fetchone()
    if res:
        return para_float(res[0]), para_float(res[1]), para_float(res[2])
    return 0.0, 0.0, 0.0

# ---- RASPAGEM DE DADOS (STATUS INVEST) ----
def extrair_indicador(soup, termos_busca):
    if isinstance(termos_busca, str):
        termos_busca = [termos_busca]

    for termo in termos_busca:
        tags_com_title = soup.find_all(
            lambda t: t.has_attr("title") and termo.lower() in t["title"].lower()
        )
        for tag in tags_com_title:
            valor_tag = tag.find("strong", class_="value") or tag.find("strong")
            if valor_tag:
                val = valor_tag.get_text(strip=True)
                if val and val != "-":
                    return val

    for termo in termos_busca:
        for tag in soup.find_all(["h3", "span", "p", "small", "b", "td", "dt"]):
            texto = tag.get_text(strip=True)
            if termo.lower() == texto.lower() or (
                termo.lower() in texto.lower() and len(texto) <= 20
            ):
                parent = tag
                for _ in range(4):
                    parent = parent.parent
                    if not parent:
                        break
                    valor_tag = parent.find("strong", class_="value") or parent.find("strong")
                    if valor_tag:
                        val = valor_tag.get_text(strip=True)
                        if val and val != "-":
                            return val
    return None

def atualizar_cotacoes():
    conn = get_connection()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://statusinvest.com.br/",
    })
    atualizados_total = 0

    # FIIs
    try:
        fundos_df = pd.read_sql("SELECT ticker FROM fundos", conn)
        for _, row in fundos_df.iterrows():
            fii = str(row["ticker"]).strip().upper()
            url = f"https://statusinvest.com.br/fundos-imobiliarios/{fii.lower()}"
            try:
                response = session.get(url, timeout=12)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    val_txt = extrair_indicador(soup, ["valor atual", "valor atual do ativo"])
                    pvp_txt = extrair_indicador(soup, ["p/vp", "pvp"])
                    dy_txt = extrair_indicador(soup, ["dividend yield", "dy"])

                    val_clean = para_float(val_txt)
                    pvp_clean = para_float(pvp_txt)
                    dy_clean = para_float(dy_txt)

                    if val_clean > 0:
                        conn.execute(
                            "UPDATE fundos SET cota_atual = ?, pvp = ?, dy = ? WHERE ticker = ?",
                            (val_clean, pvp_clean, dy_clean, fii),
                        )
                        atualizados_total += 1
            except:
                pass
    except Exception as e:
        pass

    # Ações
    try:
        acoes_df = pd.read_sql("SELECT ticker FROM acoes", conn)
        for _, row in acoes_df.iterrows():
            acao = str(row["ticker"]).strip().upper()
            url = f"https://statusinvest.com.br/acoes/{acao.lower()}"
            try:
                response = session.get(url, timeout=12)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    val_txt = extrair_indicador(soup, ["valor atual", "valor atual do ativo"])
                    dy_txt = extrair_indicador(soup, ["dividend yield", "dy"])

                    val_clean = para_float(val_txt)
                    dy_clean = para_float(dy_txt)

                    if val_clean > 0:
                        conn.execute(
                            "UPDATE acoes SET cota_atual = ?, dy = ? WHERE ticker = ?",
                            (val_clean, dy_clean, acao),
                        )
                        atualizados_total += 1
            except:
                pass
    except Exception as e:
        pass

    conn.commit()
    conn.close()

    if atualizados_total > 0:
        st.success(f"Sucesso! {atualizados_total} ativos atualizados no banco de dados.")
    else:
        st.warning("⚠️ Nenhum ativo foi atualizado. Verifique se os tickers estão corretos.")

# ---- MENU LATERAL ----
with st.sidebar:
    st.markdown(
        "<h2 style='text-align: center; color: #4DA8DA; letter-spacing: 2px;'>TECH LUVICS</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align: center; color: #888; margin-top: -10px;'>Painel de Investimentos</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    menu = option_menu(
        menu_title=None,
        options=[
            "Dashboard",
            "Controle Mensal",
            "Tabelas & Carteira",
            "Cadastro e Operações",
            "Calculadora de Juros",
            "IA Recomendações",
        ],
        icons=[
            "bar-chart-fill",
            "wallet",
            "table",
            "arrow-left-right",
            "calculator",
            "robot",
        ],
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
                "--hover-color": "transparent",
            },
            "nav-link-selected": {
                "background-color": "#1f77b4",
                "color": "white",
                "font-weight": "bold",
            },
        },
    )

NOMES_MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

# ==============================================================================
# 📊 MENU 1: DASHBOARD
# ==============================================================================
if menu == "Dashboard":
    st.title("📊 Visão Geral da Carteira")

    hoje = datetime.now()
    conn = get_connection()

    try:
        controle_raw = pd.read_sql(
            "SELECT * FROM controle ORDER BY CAST(ano AS INTEGER) DESC, CAST(mes AS INTEGER) DESC", conn
        )
        fundos_raw = pd.read_sql("SELECT * FROM fundos", conn)
        acoes_raw = pd.read_sql("SELECT * FROM acoes", conn)
        fixa_raw = pd.read_sql("SELECT * FROM renda_fixa", conn)
    except Exception as e:
        st.error(f"Erro ao consultar o banco de dados: {e}")
        controle_raw = fundos_raw = acoes_raw = fixa_raw = pd.DataFrame()
    finally:
        conn.close()

    controle_df = limpar_dataframe_numerico(controle_raw)
    fundos_df = limpar_dataframe_numerico(fundos_raw)
    acoes_df = limpar_dataframe_numerico(acoes_raw)
    fixa_df = limpar_dataframe_numerico(fixa_raw)

    if not controle_df.empty:
        controle_df["ano"] = controle_df["ano"].apply(para_float).astype(int)
        controle_df["mes"] = controle_df["mes"].apply(para_float).astype(int)

    if not fundos_df.empty:
        fundos_df["valor_mercado"] = fundos_df["num_cotas"] * fundos_df["cota_atual"]
    if not acoes_df.empty:
        acoes_df["valor_mercado"] = acoes_df["num_cotas"] * acoes_df["cota_atual"]

    caixa_atual = 0.0
    saldo_bradesco_atual = 0.0
    saldo_mp_atual = 0.0

    if not controle_df.empty:
        df_mes_atual = controle_df[
            (controle_df["ano"] == hoje.year) & (controle_df["mes"] == hoje.month)
        ]
        if not df_mes_atual.empty:
            caixa_atual = float(df_mes_atual["caixa"].iloc[0])
            saldo_bradesco_atual = float(df_mes_atual["saldo_bradesco"].iloc[0])
            saldo_mp_atual = float(df_mes_atual["saldo_mercado_pago"].iloc[0])
        else:
            caixa_atual = float(controle_df["caixa"].iloc[0])
            saldo_bradesco_atual = float(controle_df["saldo_bradesco"].iloc[0])
            saldo_mp_atual = float(controle_df["saldo_mercado_pago"].iloc[0])

    tot_fundos = float(fundos_df["valor_mercado"].sum()) if not fundos_df.empty and "valor_mercado" in fundos_df.columns else 0.0
    tot_acoes = float(acoes_df["valor_mercado"].sum()) if not acoes_df.empty and "valor_mercado" in acoes_df.columns else 0.0
    tot_fixa = float(fixa_df["total_investido"].sum()) if not fixa_df.empty and "total_investido" in fixa_df.columns else 0.0

    st.markdown("### Resumo do Patrimônio")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Caixa Atual", f"R$ {caixa_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    m2.metric("Total FIIs", f"R$ {tot_fundos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    m3.metric("Total Ações", f"R$ {tot_acoes:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    m4.metric("Total Renda Fixa", f"R$ {tot_fixa:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.markdown("---")
    
    # ---------------- BLOCO: SALDOS BANCÁRIOS APENAS NO DASHBOARD ----------------
    st.markdown("### 🏦 Saldos Bancários (Mês Atual)")
    b1, b2 = st.columns(2)
    b1.metric("Bradesco", f"R$ {saldo_bradesco_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    b2.metric("Mercado Pago", f"R$ {saldo_mp_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    
    st.markdown("---")

    # ---------------- NOVO BLOCO: CAIXINHA DE CHECKS ----------------
    with st.expander("✅ Caixinha de Contas (Mês Atual)"):
        st.markdown(f"**Contas de {NOMES_MESES.get(hoje.month, str(hoje.month))} / {hoje.year}**")

        conn_check = get_connection()
        cursor_check = conn_check.cursor()

        # Verifica se já existe registro para o mês/ano atual na tabela controle
        cursor_check.execute("""
            SELECT id, check_gympass, check_energia, check_agua, check_aluguel,
                   check_internet, check_telefone, check_spotify, check_netflix
            FROM controle WHERE ano = ? AND mes = ?
        """, (hoje.year, hoje.month))
        row_checks = cursor_check.fetchone()

        if not row_checks:
            # Se o mês ainda não foi criado no controle, cria vazio para poder dar os checks
            cursor_check.execute("INSERT INTO controle (ano, mes) VALUES (?, ?)", (hoje.year, hoje.month))
            conn_check.commit()
            cursor_check.execute("""
                SELECT id, check_gympass, check_energia, check_agua, check_aluguel,
                       check_internet, check_telefone, check_spotify, check_netflix
                FROM controle WHERE ano = ? AND mes = ?
            """, (hoje.year, hoje.month))
            row_checks = cursor_check.fetchone()

        check_cols = ["check_gympass", "check_energia", "check_agua", "check_aluguel",
                      "check_internet", "check_telefone", "check_spotify", "check_netflix"]
        check_names = ["Gympass", "Energia", "Água", "Aluguel",
                       "Internet", "Telefone", "Spotify", "Netflix"]

        # Organizando em 4 colunas para ficar compacto no dashboard
        cols = st.columns(4)
        for i, (col_name, display_name) in enumerate(zip(check_cols, check_names)):
            with cols[i % 4]:
                val_db = bool(row_checks[i+1]) # +1 porque o índice 0 é o id
                new_val = st.checkbox(display_name, value=val_db, key=f"chk_{col_name}_{hoje.month}")
                if new_val != val_db:
                    cursor_check.execute(f"UPDATE controle SET {col_name} = ? WHERE id = ?", (int(new_val), row_checks[0]))
                    conn_check.commit()
                    st.rerun()

        conn_check.close()
        
    st.markdown("---")

    st.markdown("### Composição da Carteira")
    tipo_grafico = st.selectbox(
        "Selecione o filtro do Gráfico de Pizza:",
        ["Divisão da Carteira", "Por Fundos", "Por Tipo de Fundo", "Ações", "Renda Fixa"]
    )

    fig = None
    if tipo_grafico == "Divisão da Carteira":
        df_plot = pd.DataFrame({
            "Categoria": ["Caixa", "FIIs", "Ações", "Renda Fixa"],
            "Valor": [caixa_atual, tot_fundos, tot_acoes, tot_fixa],
        })
        df_plot = df_plot[df_plot["Valor"] > 0]
        if not df_plot.empty:
            fig = px.pie(df_plot, names="Categoria", values="Valor", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
    elif tipo_grafico == "Por Fundos" and not fundos_df.empty:
        fundos_ativos = fundos_df[fundos_df["valor_mercado"] > 0]
        if not fundos_ativos.empty:
            fig = px.pie(fundos_ativos, names="ticker", values="valor_mercado", hole=0.4)
    elif tipo_grafico == "Por Tipo de Fundo" and not fundos_df.empty:
        df_grp = fundos_df.groupby("segmento", as_index=False)["valor_mercado"].sum()
        df_grp = df_grp[df_grp["valor_mercado"] > 0]
        if not df_grp.empty:
            fig = px.pie(df_grp, names="segmento", values="valor_mercado", hole=0.4)
    elif tipo_grafico == "Ações" and not acoes_df.empty:
        acoes_ativas = acoes_df[acoes_df["valor_mercado"] > 0]
        if not acoes_ativas.empty:
            fig = px.pie(acoes_ativas, names="ticker", values="valor_mercado", hole=0.4)
    elif tipo_grafico == "Renda Fixa" and not fixa_df.empty:
        fixa_ativas = fixa_df[fixa_df["total_investido"] > 0]
        if not fixa_ativas.empty:
            fig = px.pie(fixa_ativas, names="ticker", values="total_investido", hole=0.4)

    if fig:
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Sem dados para gerar o gráfico selecionado.")

    st.markdown("---")

    with st.expander("🔍 Inspecionar Registros da Tabela de Controle Mensal"):
        if not controle_df.empty:
            st.markdown("#### 🛠️ Filtros de Análise")
            col_f1, col_f2 = st.columns([1, 2])
            anos_disponiveis = sorted(controle_df["ano"].unique(), reverse=True)
            index_ano = anos_disponiveis.index(hoje.year) if hoje.year in anos_disponiveis else 0

            with col_f1:
                ano_filtro = st.selectbox("Ano", options=anos_disponiveis, index=index_ano)

            df_ano = controle_df[controle_df["ano"] == ano_filtro].copy()
            meses_disponiveis = sorted(df_ano["mes"].unique())

            mes_atual = hoje.month
            if mes_atual in meses_disponiveis:
                default_meses = [mes_atual]
            elif len(meses_disponiveis) > 0:
                default_meses = [max(meses_disponiveis)]
            else:
                default_meses = []

            with col_f2:
                meses_filtro = st.multiselect(
                    "Selecione o(s) Mês(es) para Analisar",
                    options=meses_disponiveis,
                    default=default_meses,
                    format_func=lambda x: f"{x} - {NOMES_MESES.get(int(x), str(x))}",
                )

            if meses_filtro:
                df_filtrado = df_ano[df_ano["mes"].isin(meses_filtro)].copy()
            else:
                df_filtrado = df_ano.copy()

            st.markdown("##### 📊 Totalizador Personalizado")
            
            # Ocultando saldos e checks das opções do totalizador
            colunas_ignorar = ["id", "ano", "mes", "observacao", "saldo_bradesco", "saldo_mercado_pago"]
            colunas_numericas = [
                col for col in df_filtrado.columns 
                if col not in colunas_ignorar and not col.startswith("check_")
            ]

            col_c1, col_c2 = st.columns([1, 2])
            with col_c1:
                col_selecionada = st.selectbox("Selecione a coluna para somar:", options=colunas_numericas)

            total_selecionado = df_filtrado[col_selecionada].sum() if col_selecionada else 0.0

            with col_c2:
                st.metric(
                    f"Total {str(col_selecionada).replace('_', ' ').capitalize() if col_selecionada else ''}",
                    f"R$ {total_selecionado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                )

            st.markdown("##### 📋 Registros Filtrados")
            # Removendo saldos e checks da tabela exibida no Dataframe
            colunas_para_remover = ["saldo_bradesco", "saldo_mercado_pago"] + [c for c in df_filtrado.columns if c.startswith("check_")]
            df_display = df_filtrado.drop(columns=colunas_para_remover, errors="ignore")
            st.dataframe(df_display, width="stretch")
        else:
            st.write("A tabela de controle está vazia.")


# ==============================================================================
# 📝 MENU 2: CONTROLE MENSAL
# ==============================================================================
elif menu == "Controle Mensal":
    st.title("📝 Controle Mensal")

    tab_lancar, tab_gerenciar = st.tabs(["➕ Lançamento Rápido", "✏️ Editar / Excluir Mês"])

    # --- ABA 1: SEU CÓDIGO ORIGINAL DE LANÇAMENTO ---
    with tab_lancar:
        hoje = datetime.now()

        with st.form("form_controle"):
            col1, col2 = st.columns(2)
            with col1:
                ano = st.number_input("Ano", min_value=2000, max_value=2100, value=int(hoje.year))
            with col2:
                mes = st.number_input("Mês", min_value=1, max_value=12, value=int(hoje.month))

            st.markdown("---")

            col3, col4 = st.columns(2)
            with col3:
                opcoes_colunas = [
                    "entrada", "clear", "poupanca", "caixinha",
                    "aluguel", "contas", "uber_carro", "gastos_gerais",
                ]
                coluna_alvo = st.selectbox("Adicionar valor a qual coluna?", opcoes_colunas)
            with col4:
                valor_adicionar = st.number_input("Valor a adicionar (R$)", value=0.0, step=50.0)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("**🏦 A conta bancária será descontada (ou creditada se for Entrada):**")
            
            conta_selecionada = st.radio(
                "Conta bancária",
                ["Bradesco", "Mercado Pago"],
                horizontal=True,
                label_visibility="collapsed"
            )

            st.info("💡 **Dica:** Os saldos das contas bancárias aparecem atualizados apenas na aba Dashboard.")
            btn_salvar = st.form_submit_button("💾 Salvar Lançamento", width="stretch")

            if btn_salvar:
                conn = get_connection()
                cursor = conn.cursor()

                cursor.execute("SELECT * FROM controle WHERE ano = ? AND mes = ?", (int(ano), int(mes)))
                registro = cursor.fetchone()

                cursor.execute("PRAGMA table_info(controle)")
                cols_info = cursor.fetchall()
                col_names = [info[1] for info in cols_info]

                opcoes_colunas_db = opcoes_colunas + ["saldo_bradesco", "saldo_mercado_pago"]
                valores = {c: 0.0 for c in opcoes_colunas_db}

                caixa_anterior, bradesco_ant, mp_ant = obter_saldos_mes_anterior(conn, int(ano), int(mes))

                registro_id = None
                if registro:
                    registro_id = registro[0]
                    for c in opcoes_colunas_db:
                        if c in col_names:
                            idx = col_names.index(c)
                            valores[c] = para_float(registro[idx])
                else:
                    valores["saldo_bradesco"] = bradesco_ant
                    valores["saldo_mercado_pago"] = mp_ant

                valores[coluna_alvo] += valor_adicionar

                if conta_selecionada == "Bradesco":
                    if coluna_alvo == "entrada":
                        valores["saldo_bradesco"] += valor_adicionar
                    else:
                        valores["saldo_bradesco"] -= valor_adicionar
                elif conta_selecionada == "Mercado Pago":
                    if coluna_alvo == "entrada":
                        valores["saldo_mercado_pago"] += valor_adicionar
                    else:
                        valores["saldo_mercado_pago"] -= valor_adicionar

                total_gastos = (valores["aluguel"] + valores["contas"] + valores["uber_carro"] + valores["gastos_gerais"])
                total_saida = (total_gastos + valores["caixinha"] + valores["poupanca"] + valores["clear"])
                caixa_atual_calculado = (valores["entrada"] - total_saida) + caixa_anterior

                if registro_id:
                    cursor.execute(
                        """
                        UPDATE controle 
                        SET entrada=?, clear=?, poupanca=?, caixinha=?, aluguel=?, contas=?, 
                            uber_carro=?, gastos_gerais=?, total_gastos=?, total_saida=?, caixa=?,
                            saldo_bradesco=?, saldo_mercado_pago=?
                        WHERE id=?
                        """,
                        (
                            valores["entrada"], valores["clear"], valores["poupanca"], valores["caixinha"], 
                            valores["aluguel"], valores["contas"], valores["uber_carro"], valores["gastos_gerais"], 
                            total_gastos, total_saida, caixa_atual_calculado,
                            valores["saldo_bradesco"], valores["saldo_mercado_pago"],
                            registro_id,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO controle (ano, mes, entrada, clear, poupanca, caixinha, aluguel, contas, uber_carro, gastos_gerais, total_gastos, total_saida, caixa, saldo_bradesco, saldo_mercado_pago)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(ano), int(mes), valores["entrada"], valores["clear"], valores["poupanca"], 
                            valores["caixinha"], valores["aluguel"], valores["contas"], valores["uber_carro"], 
                            valores["gastos_gerais"], total_gastos, total_saida, caixa_atual_calculado,
                            valores["saldo_bradesco"], valores["saldo_mercado_pago"]
                        ),
                    )

                conn.commit()
                conn.close()

                st.success(f"✅ Lançamento salvo no mês {mes}/{ano}! Categoria '{coluna_alvo}' atualizada (+ R$ {valor_adicionar:.2f}).")
                if conta_selecionada != "Nenhuma":
                    st.success(f"💰 O banco **{conta_selecionada}** sofreu a dedução/acréscimo invisível do valor!")

    # --- ABA 2: NOVA ÁREA DE GERENCIAMENTO ---
    with tab_gerenciar:
        st.subheader("Gerenciar Meses Fechados")
        conn = get_connection()
        df_controle = pd.read_sql("SELECT id, mes, ano, entrada, aluguel, contas, uber_carro, gastos_gerais, clear, poupanca, caixinha FROM controle ORDER BY ano DESC, mes DESC", conn)

        if not df_controle.empty:
            
            # --- NOVIDADE: Limpeza de dados para evitar os erros do Arrow e ValueError ---
            # 1. Garante que id, mes e ano sejam lidos estritamente como números inteiros (int)
            for col in ['id', 'mes', 'ano']:
                df_controle[col] = pd.to_numeric(df_controle[col], errors='coerce').fillna(0).astype(int)

            # 2. Garante que colunas financeiras virem float (substituindo vírgula por ponto do banco de dados)
            colunas_financeiras = ['entrada', 'aluguel', 'contas', 'uber_carro', 'gastos_gerais', 'clear', 'poupanca', 'caixinha']
            for col in colunas_financeiras:
                if df_controle[col].dtype == 'object':  # Se veio do SQLite como texto
                    df_controle[col] = df_controle[col].astype(str).str.replace(',', '.', regex=False)
                df_controle[col] = pd.to_numeric(df_controle[col], errors='coerce').fillna(0.0)
            # -----------------------------------------------------------------------------

            st.dataframe(df_controle, width="stretch", hide_index=True)

            opcoes = [f"{int(row['mes']):02d}/{int(row['ano'])} (ID: {int(row['id'])})" for _, row in df_controle.iterrows()]
            escolha = st.selectbox("Selecione o registro para editar/excluir:", opcoes)
            id_selecionado = int(escolha.split("ID: ")[1].replace(")", ""))

            cursor = conn.cursor()
            cursor.execute("SELECT * FROM controle WHERE id = ?", (id_selecionado,))
            registro = cursor.fetchone()
            cursor.execute("PRAGMA table_info(controle)")
            cols = [info[1] for info in cursor.fetchall()]
            dados_atuais = dict(zip(cols, registro))

            col_ed1, col_ed2 = st.columns([2, 1])
            
            with col_ed1:
                with st.form("form_editar_mes"):
                    st.markdown("### ✏️ Editar Valores Manuais")
                    colA, colB = st.columns(2)
                    with colA:
                        # Usando o seu para_float para garantir que a interface aceite os dados
                        n_ent = st.number_input("Entrada", value=para_float(dados_atuais.get("entrada", 0)), step=10.0)
                        n_alu = st.number_input("Aluguel", value=para_float(dados_atuais.get("aluguel", 0)), step=10.0)
                        n_con = st.number_input("Contas", value=para_float(dados_atuais.get("contas", 0)), step=10.0)
                        n_ubr = st.number_input("Uber/Carro", value=para_float(dados_atuais.get("uber_carro", 0)), step=10.0)
                        n_gst = st.number_input("Gastos Gerais", value=para_float(dados_atuais.get("gastos_gerais", 0)), step=10.0)
                    with colB:
                        n_clr = st.number_input("Clear", value=para_float(dados_atuais.get("clear", 0)), step=10.0)
                        n_pop = st.number_input("Poupança", value=para_float(dados_atuais.get("poupanca", 0)), step=10.0)
                        n_cai = st.number_input("Caixinha", value=para_float(dados_atuais.get("caixinha", 0)), step=10.0)
                        n_bra = st.number_input("Saldo Bradesco", value=para_float(dados_atuais.get("saldo_bradesco", 0)), step=10.0)
                        n_mer = st.number_input("Saldo M. Pago", value=para_float(dados_atuais.get("saldo_mercado_pago", 0)), step=10.0)

                    if st.form_submit_button("💾 Salvar Alterações", width="stretch"):
                        t_gastos = n_alu + n_con + n_ubr + n_gst
                        t_saida = t_gastos + n_clr + n_pop + n_cai
                        cx_ant, _, _ = obter_saldos_mes_anterior(conn, int(dados_atuais["ano"]), int(dados_atuais["mes"]))
                        novo_caixa = (n_ent - t_saida) + cx_ant

                        cursor.execute("""
                            UPDATE controle SET entrada=?, aluguel=?, contas=?, uber_carro=?, gastos_gerais=?,
                            clear=?, poupanca=?, caixinha=?, saldo_bradesco=?, saldo_mercado_pago=?,
                            total_gastos=?, total_saida=?, caixa=? WHERE id=?
                        """, (n_ent, n_alu, n_con, n_ubr, n_gst, n_clr, n_pop, n_cai, n_bra, n_mer, t_gastos, t_saida, novo_caixa, id_selecionado))
                        conn.commit()
                        st.success("✅ Mês atualizado!")
                        st.rerun()

            with col_ed2:
                st.markdown("### 🗑️ Excluir")
                st.warning("Isso apagará o mês inteiro. Ação irreversível.")
                if st.button("🚨 Excluir Mês", width="stretch"):
                    cursor.execute("DELETE FROM controle WHERE id=?", (id_selecionado,))
                    conn.commit()
                    st.success("Mês excluído!")
                    st.rerun()
        else:
            st.info("Nenhum mês cadastrado ainda.")
        conn.close()

# ==============================================================================
# 💼 MENU 3: TABELAS & CARTEIRA
# ==============================================================================
elif menu == "Tabelas & Carteira":
    st.title("💼 Carteira de Investimentos")
    conn = get_connection()

    st.subheader("1. FIIs")
    if st.button("🔄 Atualizar Cotações (StatusInvest)"):
        with st.spinner("Buscando indicadores online..."):
            atualizar_cotacoes()

    try:
        df_fundos = limpar_dataframe_numerico(pd.read_sql("SELECT * FROM fundos", conn))
        if "num_cotas" in df_fundos.columns and "cota_atual" in df_fundos.columns:
            df_fundos.insert(loc=3, column="Valor de Mercado (R$)", value=(df_fundos["num_cotas"] * df_fundos["cota_atual"]))
        st.dataframe(df_fundos, width="stretch")
    except Exception as e:
        st.warning(f"Erro ao carregar FIIs: {e}")

    st.subheader("2. Ações")
    try:
        df_acoes = limpar_dataframe_numerico(pd.read_sql("SELECT * FROM acoes", conn))
        if "num_cotas" in df_acoes.columns and "cota_atual" in df_acoes.columns:
            df_acoes.insert(loc=3, column="Valor de Mercado (R$)", value=(df_acoes["num_cotas"] * df_acoes["cota_atual"]))
        st.dataframe(df_acoes, width="stretch")
    except Exception as e:
        st.warning(f"Erro ao carregar Ações: {e}")

    st.subheader("3. Renda Fixa")
    try:
        df_fixa = limpar_dataframe_numerico(pd.read_sql("SELECT * FROM renda_fixa", conn))
        st.dataframe(df_fixa, width="stretch")
    except Exception as e:
        st.warning(f"Erro ao carregar Renda Fixa: {e}")

    conn.close()


# ==============================================================================
# ➕ MENU 4: CADASTRO E OPERAÇÕES
# ==============================================================================
# ==============================================================================
# ➕ MENU 4: CADASTRO E OPERAÇÕES
# ==============================================================================
elif menu == "Cadastro e Operações":
    st.title("➕ Cadastro e Operações")

    tab1, tab2, tab3 = st.tabs(["Adicionar Novo Ativo", "Lançar Operação", "Editar / Excluir Histórico"])
    conn = get_connection()

    # --- ABA 1 E 2: SEU CÓDIGO ORIGINAL ---
    with tab1:
        tipo_ativo_novo = st.selectbox("Selecione a Categoria para Cadastro", ["FIIs", "Ações", "Renda Fixa"], key="cat_novo")
        with st.form("form_novo"):
            nome = st.text_input("Ticker ou Nome do Ativo").upper()
            if tipo_ativo_novo == "FIIs":
                tipo_fundo = st.selectbox("Tipo", ["Titulos Mob.", "Hibrido", "Shopping", "Laje", "Galpão Logistico", "Ação", "Outro"])
            else:
                tipo_fundo = ""

            if st.form_submit_button("Cadastrar Ativo", width="stretch"):
                if nome:
                    try:
                        ticker_limpo = nome.upper().strip()
                        if tipo_ativo_novo == "FIIs":
                            conn.execute(
                                "INSERT INTO fundos (ticker, segmento, num_cotas, total_investido, cota_atual, pvp, dy) VALUES (?, ?, 0, 0, 0, 0, 0)",
                                (ticker_limpo, tipo_fundo),
                            )
                        elif tipo_ativo_novo == "Ações":
                            conn.execute(
                                "INSERT INTO acoes (ticker, num_cotas, total_investido, cota_atual, dy) VALUES (?, 0, 0, 0, 0)",
                                (ticker_limpo,),
                            )
                        else:
                            conn.execute(
                                "INSERT INTO renda_fixa (ticker, total_investido, dy) VALUES (?, 0, 0)",
                                (ticker_limpo,),
                            )
                        conn.commit()
                        st.success(f"Ativo {ticker_limpo} cadastrado com sucesso!")
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
            df_ativos = pd.DataFrame(columns=["ticker"])

        if df_ativos.empty:
            st.warning("Nenhum ativo cadastrado nesta categoria.")
        else:
            with st.form("form_op"):
                ativo_selecionado = st.selectbox("Ativo", df_ativos["ticker"].tolist())
                tipo_op = st.selectbox("Tipo de Ordem", ["Compra", "Venda"])
                data_op = st.date_input("Data")

                if tipo_ativo_op in ["FIIs", "Ações"]:
                    qtd = st.number_input("Quantidade de Cotas", min_value=0.01, step=1.0)
                else:
                    val_total = st.number_input("Valor Transacionado (R$)", min_value=1.0, step=100.0)
                    qtd = 1.0

                if st.form_submit_button("Salvar Operação", width="stretch"):
                    multiplicador = 1 if tipo_op == "Compra" else -1
                    cursor = conn.cursor()
                    data_str = data_op.strftime("%Y-%m-%d")

                    try:
                        if tipo_ativo_op in ["FIIs", "Ações"]:
                            cursor.execute(f"SELECT cota_atual, num_cotas, total_investido FROM {tabela} WHERE ticker = ?", (ativo_selecionado,))
                            res = cursor.fetchone()
                            cota_atual = para_float(res[0]) if res else 0.0
                            num_cotas_atuais = para_float(res[1]) if res else 0.0
                            tot_investido_atual = para_float(res[2]) if res else 0.0

                            valor_unitario = cota_atual
                            valor_total = float(qtd) * valor_unitario
                            novas_cotas = max(0.0, num_cotas_atuais + (float(qtd) * multiplicador))
                            novo_tot_investido = (tot_investido_atual + valor_total if multiplicador == 1 else max(0.0, tot_investido_atual - valor_total))

                            cursor.execute(f"UPDATE {tabela} SET num_cotas = ?, total_investido = ? WHERE ticker = ?", (novas_cotas, novo_tot_investido, ativo_selecionado))
                            cursor.execute(
                                "INSERT INTO operacoes (ticker, data_op, tipo, quantidade, valor_unitario, valor_total) VALUES (?, ?, ?, ?, ?, ?)",
                                (ativo_selecionado, data_str, tipo_op, float(qtd), valor_unitario, valor_total),
                            )
                        else:
                            cursor.execute("SELECT total_investido FROM renda_fixa WHERE ticker = ?", (ativo_selecionado,))
                            res = cursor.fetchone()
                            tot_investido_atual = para_float(res[0]) if res else 0.0
                            valor_unitario = float(val_total)
                            valor_total = float(val_total)
                            novo_tot_investido = max(0.0, tot_investido_atual + (valor_total * multiplicador))

                            cursor.execute("UPDATE renda_fixa SET total_investido = ? WHERE ticker = ?", (novo_tot_investido, ativo_selecionado))
                            cursor.execute(
                                "INSERT INTO operacoes (ticker, data_op, tipo, quantidade, valor_unitario, valor_total) VALUES (?, ?, ?, ?, ?, ?)",
                                (ativo_selecionado, data_str, tipo_op, 1.0, valor_unitario, valor_total),
                            )

                        conn.commit()
                        st.success(f"✅ Operação realizada para {ativo_selecionado}!")
                    except Exception as e:
                        st.error(f"Erro ao processar operação: {e}")

    # --- ABA 3: NOVA ÁREA DE GERENCIAMENTO ---
    with tab3:
        st.subheader("Gerenciar Histórico e Ativos")
        
        escolha_gerenciar = st.radio("O que deseja editar/excluir?", ["Operações (Histórico)", "Ativos da Carteira"], horizontal=True)

        if escolha_gerenciar == "Operações (Histórico)":
            df_ops = pd.read_sql("SELECT id, ticker, data_op, tipo, quantidade, valor_total FROM operacoes ORDER BY id DESC", conn)
            if not df_ops.empty:
                st.dataframe(df_ops, width="stretch", hide_index=True)
                
                opcoes_op = [f"ID: {row['id']} | {row['ticker']} - {row['tipo']} ({row['data_op']})" for _, row in df_ops.iterrows()]
                op_selecionada = st.selectbox("Selecione a operação para excluir:", opcoes_op)
                id_op = int(op_selecionada.split(" |")[0].replace("ID: ", ""))

                st.info("💡 **Dica:** Excluir uma operação não altera o saldo do ativo na carteira. Se precisar, ajuste o saldo do ativo na opção 'Ativos da Carteira' acima.")
                
                if st.button("🗑️ Excluir Operação", type="primary"):
                    conn.execute("DELETE FROM operacoes WHERE id = ?", (id_op,))
                    conn.commit()
                    st.success("Operação excluída do histórico!")
                    st.rerun()
            else:
                st.info("Nenhuma operação registrada.")

        elif escolha_gerenciar == "Ativos da Carteira":
            cat_ativo = st.selectbox("Categoria do Ativo", ["fundos", "acoes", "renda_fixa"])
            
            if cat_ativo == "renda_fixa":
                df_ativos_cad = pd.read_sql(f"SELECT ticker, total_investido FROM {cat_ativo}", conn)
            else:
                df_ativos_cad = pd.read_sql(f"SELECT ticker, num_cotas, total_investido FROM {cat_ativo}", conn)

            if not df_ativos_cad.empty:
                st.dataframe(df_ativos_cad, width="stretch", hide_index=True)
                ticker_del = st.selectbox("Selecione o ativo:", df_ativos_cad["ticker"].tolist())

                cursor = conn.cursor()
                if cat_ativo != "renda_fixa":
                    cursor.execute(f"SELECT num_cotas, total_investido FROM {cat_ativo} WHERE ticker = ?", (ticker_del,))
                    dados_ativo = cursor.fetchone()
                    n_cotas_atual = float(dados_ativo[0])
                    t_inv_atual = float(dados_ativo[1])
                else:
                    cursor.execute(f"SELECT total_investido FROM {cat_ativo} WHERE ticker = ?", (ticker_del,))
                    dados_ativo = cursor.fetchone()
                    n_cotas_atual = 0.0
                    t_inv_atual = float(dados_ativo[0])

                col_atv1, col_atv2 = st.columns([2, 1])
                
                with col_atv1:
                    with st.form("form_editar_ativo"):
                        st.markdown(f"### ✏️ Ajustar Saldos ({ticker_del})")
                        if cat_ativo != "renda_fixa":
                            n_cotas_nova = st.number_input("Número de Cotas Corrigido", value=n_cotas_atual, step=1.0)
                        else:
                            n_cotas_nova = 0.0
                        t_investido_novo = st.number_input("Total Investido Corrigido (R$)", value=t_inv_atual, step=10.0)

                        if st.form_submit_button("💾 Salvar Correção", width="stretch"):
                            if cat_ativo != "renda_fixa":
                                cursor.execute(f"UPDATE {cat_ativo} SET num_cotas = ?, total_investido = ? WHERE ticker = ?", (n_cotas_nova, t_investido_novo, ticker_del))
                            else:
                                cursor.execute(f"UPDATE {cat_ativo} SET total_investido = ? WHERE ticker = ?", (t_investido_novo, ticker_del))
                            conn.commit()
                            st.success("Saldos do ativo corrigidos!")
                            st.rerun()

                with col_atv2:
                    st.markdown("### 🗑️ Excluir Ativo")
                    st.warning("Remove o ativo da carteira.")
                    if st.button("🚨 Excluir", width="stretch"):
                        cursor.execute(f"DELETE FROM {cat_ativo} WHERE ticker = ?", (ticker_del,))
                        conn.commit()
                        st.success("Ativo removido!")
                        st.rerun()
            else:
                st.info("Nenhum ativo nesta categoria.")

    conn.close()

# ==============================================================================
# 🧮 MENU 5: CALCULADORA DE JUROS
# ==============================================================================
elif menu == "Calculadora de Juros":
    st.title("🧮 Calculadora de Juros Compostos")

    with st.form("form_calc"):
        col1, col2 = st.columns(2)
        with col1:
            v_inicial = st.number_input("Aporte Inicial (R$)", min_value=0.0, value=1000.0, step=100.0)
            v_mensal = st.number_input("Aporte Mensal (R$)", min_value=0.0, value=100.0, step=50.0)
        with col2:
            taxa_juros = st.number_input("Taxa de Juros ao Mês (%)", min_value=0.0, value=1.0, step=0.1)
            meses = st.number_input("Tempo em Meses", min_value=1, value=12, step=1)

        btn_calc = st.form_submit_button("Calcular", width="stretch")

        if btn_calc:
            montante = v_inicial
            for _ in range(int(meses)):
                montante = montante * (1 + (taxa_juros / 100)) + v_mensal
            
            lucro = montante - (v_inicial + (v_mensal * meses))

            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric("💰 Valor Final Total", f"R$ {montante:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            c2.metric("📈 Apenas Juros Rendidos", f"R$ {lucro:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))


# ==============================================================================
# 🤖 MENU 6: IA RECOMENDAÇÕES
# ==============================================================================
elif menu == "IA Recomendações":
    st.title("🤖 IA & Recomendações de Carteira")
    st.write("Utilize a Inteligência Artificial para analisar sua carteira, evitar armadilhas e descobrir onde aportar seu dinheiro com base no cenário atual.")

    # --- ENTRADA DE DADOS DO USUÁRIO ---
    st.subheader("⚙️ Parâmetros do Aporte")
    col1, col2 = st.columns(2)
    with col1:
        valor_aporte = st.number_input("Quanto você quer investir agora? (R$)", min_value=10.0, value=300.0, step=50.0)
    with col2:
        qtd_ativos = st.number_input("Em quantos ativos deseja dividir esse valor?", min_value=1, max_value=10, value=3, step=1)
    
    chave_api = st.text_input("🔑 Chave API do Google Gemini (pegue grátis no Google AI Studio)", type="password", help="Acesse aistudio.google.com para gerar sua chave.")

    if st.button("🧠 Gerar Cenários e Recomendações", type="primary"):
        if not chave_api:
            st.warning("⚠️ Insira sua Chave de API do Gemini para utilizar a Inteligência Artificial.")
        else:
            with st.spinner("A IA está analisando seus ativos, cruzando dados de mercado e buscando armadilhas ocultas. Aguarde..."):
                try:
                    # 1. Configurar a API
                    import google.generativeai as genai
                    genai.configure(api_key=chave_api)
                    
                    # 2. Coletar os dados da sua carteira no Banco de Dados
                    conn = get_connection()
                    
                    try:
                        df_acoes = pd.read_sql("SELECT * FROM acoes", conn)
                        str_acoes = df_acoes.to_dict(orient="records") if not df_acoes.empty else "Nenhuma ação cadastrada."
                    except: str_acoes = "Tabela de ações indisponível."
                    
                    try:
                        df_fiis = pd.read_sql("SELECT * FROM fundos", conn)
                        str_fiis = df_fiis.to_dict(orient="records") if not df_fiis.empty else "Nenhum FII cadastrado."
                    except: str_fiis = "Tabela de FIIs indisponível."
                    
                    try:
                        df_rf = pd.read_sql("SELECT * FROM renda_fixa", conn)
                        str_rf = df_rf.to_dict(orient="records") if not df_rf.empty else "Nenhuma Renda Fixa cadastrada."
                    except: str_rf = "Tabela de RF indisponível."
                    
                    conn.close()

                    # 3. Criar o Comando (Prompt) Avançado para a IA
                    prompt = f"""
                    Você é um analista financeiro sênior, especialista no mercado brasileiro (B3), FIIs e macroeconomia.
                    Seu cliente tem R$ {valor_aporte:.2f} para investir hoje e quer dividir esse dinheiro em EXATAMENTE {qtd_ativos} ativos.

                    Aqui estão os ativos que ele já possui na carteira e acompanha (avalie estes preferencialmente, mas pode sugerir outros caso a carteira atual seja muito ruim):
                    Ações: {str_acoes}
                    FIIs: {str_fiis}
                    Renda Fixa: {str_rf}

                    Crie um relatório completo com:
                    1. CENÁRIO CONSERVADOR: Focado em segurança, previsibilidade e proteção (dividendos constantes, empresas consolidadas, FIIs de tijolo resilientes).
                       - Escolha {qtd_ativos} ativos.
                       - Diga exatamente quantos Reais (R$) colocar em cada um (a soma deve dar R$ {valor_aporte}).
                       - Justifique profundamente.
                    
                    2. CENÁRIO ARROJADO: Focado em ganho de capital, assimetria de valor e risco calculado.
                       - Escolha {qtd_ativos} ativos.
                       - Diga exatamente quantos Reais (R$) colocar em cada um.
                       - Justifique profundamente.

                    REGRAS CRÍTICAS DE ANÁLISE:
                    - NÃO olhe apenas para o P/VP e o Dividend Yield. Se um P/VP está muito baixo (ex: < 0.70), explique o porquê. Pode ser risco de inadimplência (calote em CRIs no caso de FIIs de papel), vacância alta, ou empresa em risco financeiro. Identifique se é uma oportunidade (assimetria) ou uma 'Value Trap' (Armadilha de Valor).
                    - Traga contexto do mundo real: juros atuais (Selic), inflação e cenário econômico no Brasil que impactem essas escolhas.
                    - Formate a resposta usando Markdown, deixando o texto bonito, com emojis e bem espaçado para leitura fácil.
                    """

                    # 4. Busca dinâmica de modelos disponíveis diretamente na sua chave de API
                    status_texto = st.empty()
                    status_texto.info("🔍 Consultando modelos disponíveis na sua conta...")

                    resposta = None
                    ultimo_erro = ""

                    try:
                        # Lista todos os modelos ativos que suportam a geração de texto (generateContent)
                        modelos_disponiveis = [
                            m.name for m in genai.list_models()
                            if 'generateContent' in m.supported_generation_methods
                        ]

                        if not modelos_disponiveis:
                            raise Exception("Nenhum modelo ativo foi encontrado para esta chave de API.")

                        # Prioriza modelos do tipo 'flash' (mais rápidos e dentro do plano gratuito)
                        modelos_ordenados = sorted(
                            modelos_disponiveis,
                            key=lambda x: 0 if 'flash' in x.lower() else 1
                        )

                        for m_full_name in modelos_ordenados:
                            nome_modelo = m_full_name.replace("models/", "")
                            try:
                                status_texto.info(f"🔄 Testando conexão com: {nome_modelo}...")
                                modelo_ia = genai.GenerativeModel(nome_modelo)
                                resposta = modelo_ia.generate_content(prompt, request_options={"timeout": 35})
                                status_texto.empty()
                                break
                            except Exception as err:
                                ultimo_erro = str(err)
                                continue

                    except Exception as e_list:
                        ultimo_erro = str(e_list)

                    if resposta is None:
                        status_texto.empty()
                        raise Exception(f"Nenhum modelo liberado respondeu. Detalhe: {ultimo_erro}")

                    # 5. Mostrar o resultado na tela
                    st.success("✅ Análise concluída com sucesso!")
                    st.markdown("---")
                    st.markdown(resposta.text)
                    st.markdown("---")
                    st.caption("Aviso Legal: A IA fornece análises baseadas em dados e cenários, mas não substitui a responsabilidade final do investidor. Renda variável envolve riscos.")

                except Exception as e:
                    st.error(f"Ocorreu um erro ao conectar com a IA: {e}")

    # --- VISÃO QUANTITATIVA BÁSICA (Backup offline) ---
    st.markdown("---")
    st.subheader("📊 Filtro Rápido do Sistema (Offline)")
    with st.expander("Ver filtro apenas matemático (P/VP descontado)"):
        conn = get_connection()
        try:
            df_f = limpar_dataframe_numerico(pd.read_sql("SELECT * FROM fundos", conn))
            if not df_f.empty and "pvp" in df_f.columns:
                descontados = df_f[(df_f["pvp"] > 0) & (df_f["pvp"] < 1.0) & (df_f["num_cotas"] > 0)]
                if not descontados.empty:
                    st.write("💡 FIIs na carteira com P/VP < 1.0 (Atenção: Necessário análise qualitativa, não invista só por isso):")
                    st.dataframe(descontados[["ticker", "segmento", "pvp", "dy", "cota_atual"]], width="stretch")
                else:
                    st.info("Nenhum FII descontado encontrado.")
        except:
            pass
        finally:
            conn.close()
