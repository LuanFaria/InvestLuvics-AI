import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
import requests
from bs4 import BeautifulSoup

DB_PATH = 'carteira_fiis.db'

# ==========================================
# 1. INICIALIZAÇÃO DO BANCO DE DADOS
# ==========================================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS controle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ano INTEGER,
            mes TEXT,
            entrada REAL,
            caixa REAL,
            clear REAL,
            poupanca REAL,
            caixinha REAL,
            aluguel REAL,
            contas REAL,
            uber_carro REAL,
            gastos_gerais REAL,
            total_gastos REAL,
            total_saida REAL,
            quantidade_cotas INTEGER
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS fundos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            tp_fundo TEXT,
            quantidade_cotas INTEGER,
            p_vp REAL,
            dy REAL,
            valor_atual_cota REAL,
            valor_patrimonio REAL,
            total_investido REAL,
            porcentagem_patrimonio REAL
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS acoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_acao TEXT UNIQUE,
            total_investido REAL,
            dy REAL
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS renda_fixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_renda TEXT UNIQUE,
            total_investido REAL,
            porcentagem_rendimento REAL
        )''')
        conn.commit()

init_db()

# ==========================================
# 2. FUNÇÃO DE RASPAGEM AUTOMÁTICA (FIIs)
# ==========================================
def buscar_dados_statusinvest(ticker):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = f"https://statusinvest.com.br/fundos-imobiliarios/{ticker.lower().strip()}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Valor Atual da Cota
        val_elem = soup.find('div', {'class': 'info value'})
        valor_cota = 0.0
        if val_elem:
            val_txt = val_elem.find('strong').text.strip().replace('R$', '').replace('.', '').replace(',', '.')
            valor_cota = float(val_txt)
            
        # P/VP
        p_vp = 1.0
        divs_indicators = soup.find_all('div', {'class': 'card'})
        for d in divs_indicators:
            title = d.find('h3')
            if title and 'P/VP' in title.text:
                val_strong = d.find('strong')
                if val_strong:
                    p_vp = float(val_strong.text.strip().replace(',', '.'))
                    
        # Dividend Yield (DY)
        dy = 0.0
        for d in divs_indicators:
            title = d.find('h3')
            if title and 'DIVIDEND YIELD' in title.text.upper():
                val_strong = d.find('strong')
                if val_strong:
                    dy_txt = val_strong.text.strip().replace('%', '').replace(',', '.')
                    dy = float(dy_txt)
                    
        return {
            'valor_atual_cota': valor_cota,
            'p_vp': p_vp,
            'dy': dy
        }
    except Exception as e:
        return None

# ==========================================
# 3. INTERFACE STREAMLIT
# ==========================================
st.set_page_config(page_title="Gestão Patrimonial e Investimentos", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        padding: 25px; border-radius: 14px; color: white;
        margin-bottom: 25px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    }
    .main-header h1 { color: #FFFFFF !important; margin: 0; font-size: 1.8rem; }
    .main-header p { color: #94A3B8 !important; margin: 5px 0 0 0; }
    </style>
""", unsafe_allow_html=True)

menu = st.sidebar.selectbox("🗺️ Navegação", [
    "Dashboard", 
    "Controle Mensal", 
    "Cadastrar Ativos (Banco)", 
    "Relatórios & Exportação"
])

st.markdown("""
    <div class="main-header">
        <h1>Painel de Controle Financeiro</h1>
        <p>Gerenciamento Integrado de Patrimônio, Orçamento e Ativos</p>
    </div>
""", unsafe_allow_html=True)

TIPOS_FUNDO_OPCOES = [
    "Titulos Mob.", 
    "Hibrido", 
    "Shopping", 
    "Laje", 
    "Galpão Logistico", 
    "Ação", 
    "Outros"
]

# ==========================================
# TELA 1: DASHBOARD
# ==========================================
if menu == "Dashboard":
    st.subheader("📊 Visão Geral do Patrimônio")
    
    with sqlite3.connect(DB_PATH) as conn:
        df_fundos = pd.read_sql_query("SELECT * FROM fundos", conn)
        df_acoes = pd.read_sql_query("SELECT * FROM acoes", conn)
        df_rf = pd.read_sql_query("SELECT * FROM renda_fixa", conn)

    total_patrimonio_fundos = df_fundos['valor_patrimonio'].sum() if not df_fundos.empty else 0.0
    total_investido_acoes = df_acoes['total_investido'].sum() if not df_acoes.empty else 0.0
    total_investido_rf = df_rf['total_investido'].sum() if not df_rf.empty else 0.0
    patrimonio_total = total_patrimonio_fundos + total_investido_acoes + total_investido_rf

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Patrimônio Total", f"R$ {patrimonio_total:,.2f}")
    with col2:
        st.metric("Total em FIIs", f"R$ {total_patrimonio_fundos:,.2f}")
    with col3:
        st.metric("Total em Ações", f"R$ {total_investido_acoes:,.2f}")
    with col4:
        st.metric("Total em Renda Fixa", f"R$ {total_investido_rf:,.2f}")

    st.write("---")
    col_g1, col_g2, col_g3 = st.columns(3)
    
    with col_g1:
        st.markdown("##### 🏢 Fundos & FIIs")
        if not df_fundos.empty:
            st.dataframe(df_fundos[['nome', 'tp_fundo', 'quantidade_cotas', 'valor_patrimonio']], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum FII cadastrado.")

    with col_g2:
        st.markdown("##### 📈 Ações")
        if not df_acoes.empty:
            st.dataframe(df_acoes, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma ação cadastrada.")

    with col_g3:
        st.markdown("##### 🔒 Renda Fixa")
        if not df_rf.empty:
            st.dataframe(df_rf, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma renda fixa cadastrada.")

# ==========================================
# TELA 2: CONTROLE MENSAL
# ==========================================
elif menu == "Controle Mensal":
    st.subheader("📅 Controle Orçamentário Mensal")
    
    with st.form("form_controle"):
        col1, col2, col3 = st.columns(3)
        ano = col1.number_input("Ano", min_value=2020, max_value=2035, value=datetime.now().year)
        mes = col2.selectbox("Mês", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])
        quantidade_cotas = col3.number_input("Quantidade de Cotas (Acumulada/Mês)", min_value=0, step=1)
        
        st.write("---")
        c_a, c_b, c_c = st.columns(3)
        entrada = c_a.number_input("Entrada (Salário R$)", min_value=0.0, step=100.0)
        caixa = c_b.number_input("Caixa (Mercado Pago + Bradesco R$)", min_value=0.0, step=100.0)
        clear = c_c.number_input("Clear (Investido no mês R$)", min_value=0.0, step=100.0)
        
        c_d, c_e, c_f = st.columns(3)
        poupanca = c_d.number_input("Poupança (R$)", min_value=0.0, step=100.0)
        caixinha = c_e.number_input("Caixinha (R$)", min_value=0.0, step=100.0)
        aluguel = c_f.number_input("Aluguel (R$)", min_value=0.0, step=100.0)
        
        c_g, c_h, c_i = st.columns(3)
        contas = c_g.number_input("Contas (Água, Luz, Net R$)", min_value=0.0, step=50.0)
        uber_carro = c_h.number_input("Uber / Carro (R$)", min_value=0.0, step=50.0)
        gastos_gerais = c_i.number_input("Gastos Gerais (R$)", min_value=0.0, step=50.0)
        
        submit_controle = st.form_submit_button("Salvar / Atualizar Mês")
        
        if submit_controle:
            total_gastos = aluguel + contas + uber_carro + gastos_gerais
            total_saida = total_gastos + clear + poupanca + caixa
            
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM controle WHERE ano=? AND mes=?", (ano, mes))
                existe = c.fetchone()
                
                if existe:
                    c.execute("""UPDATE controle SET entrada=?, caixa=?, clear=?, poupanca=?, caixinha=?, 
                                 aluguel=?, contas=?, uber_carro=?, gastos_gerais=?, total_gastos=?, total_saida=?, quantidade_cotas=? 
                                 WHERE ano=? AND mes=?""",
                              (entrada, caixa, clear, poupanca, caixinha, aluguel, contas, uber_carro, gastos_gerais, total_gastos, total_saida, quantidade_cotas, ano, mes))
                else:
                    c.execute("""INSERT INTO controle (ano, mes, entrada, caixa, clear, poupanca, caixinha, 
                                 aluguel, contas, uber_carro, gastos_gerais, total_gastos, total_saida, quantidade_cotas)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (ano, mes, entrada, caixa, clear, poupanca, caixinha, aluguel, contas, uber_carro, gastos_gerais, total_gastos, total_saida, quantidade_cotas))
                conn.commit()
            st.success("✅ Controle mensal salvo com sucesso!")

    st.write("---")
    st.subheader("📋 Histórico de Controle Mensal")
    with sqlite3.connect(DB_PATH) as conn:
        df_hist = pd.read_sql_query("SELECT * FROM controle ORDER BY ano DESC, id DESC", conn)
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum registro de controle mensal encontrado.")

# ==========================================
# TELA 3: CADASTRAR ATIVOS (PÁGINA ÚNICA)
# ==========================================
elif menu == "Cadastrar Ativos (Banco)":
    st.subheader("➕ Cadastro e Gerenciamento de Ativos no Banco")
    
    # 3 Botões / Seleção Principal
    tipo_ativo = st.radio("Selecione o tipo de ativo para adicionar ou gerenciar:", ["FIIs", "Ação", "Renda Fixa"], horizontal=True)
    
    st.write("---")
    
    # --- SEÇÃO DE FIIs ---
    if tipo_ativo == "FIIs":
        st.markdown("##### 🏢 Gerenciamento de FIIs")
        
        tab_f1, tab_f2 = st.tabs(["Adicionar / Atualizar FII", "Vender / Remover FII"])
        
        with tab_f1:
            with st.form("form_fundo_unico"):
                nome_fii = st.text_input("Nome / Ticker do Fundo (Ex: HGLG11)").upper().strip()
                tp_fundo = st.selectbox("Tipo do Fundo", TIPOS_FUNDO_OPCOES)
                
                col_b1, col_b2 = st.columns(2)
                buscar_auto = col_b1.form_submit_button("🔍 Puxar Dados Automaticamente")
                salvar_fii = col_b2.form_submit_button("💾 Salvar Fundo no Banco", type="primary")
                
                if 'fii_data' not in st.session_state:
                    st.session_state.fii_data = {'p_vp': 1.0, 'dy': 0.0, 'valor_atual_cota': 0.0}
                
                if buscar_auto and nome_fii:
                    with st.spinner(f"Buscando dados de {nome_fii}..."):
                        dados = buscar_dados_statusinvest(nome_fii)
                        if dados:
                            st.session_state.fii_data = dados
                            st.success(f"Dados obtidos com sucesso para {nome_fii}!")
                        else:
                            st.warning("Não foi possível buscar automaticamente. Preencha os campos abaixo.")
                
                p_vp = st.number_input("P/VP", min_value=0.0, step=0.01, value=float(st.session_state.fii_data['p_vp']))
                dy = st.number_input("DY (%)", min_value=0.0, step=0.01, value=float(st.session_state.fii_data['dy']))
                valor_atual_cota = st.number_input("Valor Atual da Cota (R$)", min_value=0.0, step=0.01, value=float(st.session_state.fii_data['valor_atual_cota']))
                quantidade_cotas = st.number_input("Quantidade de Cotas", min_value=0, step=1)
                total_investido = st.number_input("Total Investido (R$)", min_value=0.0, step=10.0)
                
                if salvar_fii and nome_fii:
                    valor_patrimonio = quantidade_cotas * valor_atual_cota
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("""INSERT INTO fundos (nome, tp_fundo, quantidade_cotas, p_vp, dy, valor_atual_cota, valor_patrimonio, total_investido, porcentagem_patrimonio)
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0)
                                     ON CONFLICT(nome) DO UPDATE SET 
                                     tp_fundo=excluded.tp_fundo, quantidade_cotas=excluded.quantidade_cotas, 
                                     p_vp=excluded.p_vp, dy=excluded.dy, valor_atual_cota=excluded.valor_atual_cota, 
                                     valor_patrimonio=excluded.valor_patrimonio, total_investido=excluded.total_investido""",
                                  (nome_fii, tp_fundo, quantidade_cotas, p_vp, dy, valor_atual_cota, valor_patrimonio, total_investido))
                        conn.commit()
                    st.success(f"✅ FII {nome_fii} salvo com sucesso!")
                    st.rerun()

        with tab_f2:
            with sqlite3.connect(DB_PATH) as conn:
                df_f = pd.read_sql_query("SELECT nome FROM fundos", conn)
            if not df_f.empty:
                fundo_rem = st.selectbox("Selecione o FII para vender/remover", df_f['nome'].tolist())
                if st.button("Confirmar Venda / Exclusão do FII", type="primary"):
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM fundos WHERE nome=?", (fundo_rem,))
                        conn.commit()
                    st.success(f"🗑️ FII {fundo_rem} removido da carteira.")
                    st.rerun()
            else:
                st.info("Nenhum FII cadastrado.")

    # --- SEÇÃO DE AÇÃO ---
    elif tipo_ativo == "Ação":
        st.markdown("##### 📈 Gerenciamento de Ações")
        
        tab_a1, tab_a2 = st.tabs(["Adicionar / Atualizar Ação", "Vender / Remover Ação"])
        
        with tab_a1:
            with st.form("form_acao_unico"):
                nome_acao = st.text_input("Nome da Ação (Ex: PETR4)").upper().strip()
                total_investido = st.number_input("Total Investido (R$)", min_value=0.0, step=10.0)
                dy = st.number_input("DY (%)", min_value=0.0, step=0.01)
                
                submit_acao = st.form_submit_button("Salvar Ação no Banco", type="primary")
                
                if submit_acao and nome_acao:
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("""INSERT INTO acoes (nome_acao, total_investido, dy) VALUES (?, ?, ?)
                                     ON CONFLICT(nome_acao) DO UPDATE SET total_investido=excluded.total_investido, dy=excluded.dy""",
                                  (nome_acao, total_investido, dy))
                        conn.commit()
                    st.success(f"✅ Ação {nome_acao} salva com sucesso!")
                    st.rerun()
                    
        with tab_a2:
            with sqlite3.connect(DB_PATH) as conn:
                df_ac = pd.read_sql_query("SELECT nome_acao FROM acoes", conn)
            if not df_ac.empty:
                acao_rem = st.selectbox("Selecione a ação para vender/remover", df_ac['nome_acao'].tolist())
                if st.button("Confirmar Venda / Exclusão da Ação", type="primary"):
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM acoes WHERE nome_acao=?", (acao_rem,))
                        conn.commit()
                    st.success(f"🗑️ Ação {acao_rem} removida.")
                    st.rerun()
            else:
                st.info("Nenhuma ação cadastrada.")

    # --- SEÇÃO DE RENDA FIXA ---
    else:
        st.markdown("##### 🔒 Gerenciamento de Renda Fixa")
        
        tab_r1, tab_r2 = st.tabs(["Adicionar / Atualizar Renda Fixa", "Remover Renda Fixa"])
        
        with tab_r1:
            with st.form("form_rf_unico"):
                nome_renda = st.text_input("Nome da Renda (Ex: Tesouro Selic 2029, CDB IPCA+, Poupança)").strip()
                tanto_investido = st.number_input("Tanto Investido (R$)", min_value=0.0, step=10.0)
                porcentagem_rendimento = st.number_input("Porcentagem de Rendimento (Ex: 100% CDI, 6% IPCA)", min_value=0.0, step=0.01)
                
                submit_rf = st.form_submit_button("Salvar Renda Fixa no Banco", type="primary")
                
                if submit_rf and nome_renda:
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("""INSERT INTO renda_fixa (nome_renda, total_investido, porcentagem_rendimento) VALUES (?, ?, ?)
                                     ON CONFLICT(nome_renda) DO UPDATE SET total_investido=excluded.total_investido, porcentagem_rendimento=excluded.porcentagem_rendimento""",
                                  (nome_renda, tanto_investido, porcentagem_rendimento))
                        conn.commit()
                    st.success(f"✅ Renda Fixa '{nome_renda}' salvo com sucesso!")
                    st.rerun()
                    
        with tab_r2:
            with sqlite3.connect(DB_PATH) as conn:
                df_rf_tab = pd.read_sql_query("SELECT nome_renda FROM renda_fixa", conn)
            if not df_rf_tab.empty:
                rf_rem = st.selectbox("Selecione a renda fixa para remover", df_rf_tab['nome_renda'].tolist())
                if st.button("Confirmar Exclusão da Renda Fixa", type="primary"):
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM renda_fixa WHERE nome_renda=?", (rf_rem,))
                        conn.commit()
                    st.success(f"🗑️ Renda Fixa '{rf_rem}' removida.")
                    st.rerun()
            else:
                st.info("Nenhuma renda fixa cadastrada.")

# ==========================================
# TELA 4: RELATÓRIOS & EXPORTAÇÃO
# ==========================================
elif menu == "Relatórios & Exportação":
    st.subheader("📥 Exportação de Dados para Excel")
    
    with sqlite3.connect(DB_PATH) as conn:
        df_controle = pd.read_sql_query("SELECT * FROM controle", conn)
        df_fundos = pd.read_sql_query("SELECT * FROM fundos", conn)
        df_acoes = pd.read_sql_query("SELECT * FROM acoes", conn)
        df_rf = pd.read_sql_query("SELECT * FROM renda_fixa", conn)
        
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_controle.to_excel(writer, index=False, sheet_name='Controle')
        df_fundos.to_excel(writer, index=False, sheet_name='Fundos_FIIs')
        df_acoes.to_excel(writer, index=False, sheet_name='Acoes')
        df_rf.to_excel(writer, index=False, sheet_name='Renda_Fixa')
        
    st.download_button(
        label="📥 Baixar Planilha Completa em Excel",
        data=buffer.getvalue(),
        file_name="Gestao_Patrimonial_Completa.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )