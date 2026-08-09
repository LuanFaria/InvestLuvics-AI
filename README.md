# 📊 InvestLuvics-AI  — Personal Finance & Asset Intelligence

> Dashboard analítico e sistema de recomendação financeira alimentado por IA para gestão de fluxo de caixa, alocação de ativos e rebalanceamento de carteira.

---

## 📌 Sobre o Projeto

O **InvestLuvics-AI ** é uma plataforma integrada de gestão financeira pessoal e análise de investimentos desenvolvida para substituir planilhas complexas por um banco de dados estruturado, uma interface interativa (estilo Power BI/Streamlit) e um **motor de recomendação com Inteligência Artificial**.

O sistema combina controle de caixa pessoal com dados de mercado capturados em tempo real (via web scraping) para sugerir aportes inteligentes, manter a carteira de investimentos equilibrada e simular projeções de independência financeira.

---

## 🛠️ Módulos e Funcionalidades

### 💵 1. Gestão de Fluxo de Caixa (Controle)
- **Receitas e Despesas:** Registro detalhado de ganhos de projetos/trabalhos e categorização de gastos (contas fixas, veículo, mercado, moradia).
- **Aportes e Sobra:** Mapeamento do valor líquido disponível mês a mês para caixa, poupança e novos aportes.

### 🏢 2. Carteira de FIIs & Rebalanceamento
- **Scraping Automático:** Captura de dados em tempo real (Cotação, P/VP, Dividend Yield) via Status Invest sem dependência de navegadores.
- **Distribuição por Categoria:** Monitoramento visual de exposição por segmentos (Papel, Lajes Corporativas, Shoppings, Híbrido, Títulos Imobiliários).
- **Metas de Alocação:** Comparativo entre o peso atual de cada fundo/setor e a meta desejada para mitigação de riscos.

### 📈 3. Renda Fixa, Ações & Outros Ativos
- **Renda Fixa:** Acompanhamento de Tesouro Direto, CDBs, pré-fixados e Caixinhas com rendimento atrelado à inflação/CDI.
- **Ações e Cripto:** Registro de posições em ações (ex: TAEE3, BBAS3) e criptoativos.

### 🧮 4. Calculadora de Investimentos & Projeções
- Simulador de juros compostos para estimativa de rentabilidade acumulada, meta de patrimônio e tempo estimado para atingimento de independência financeira.

### 🤖 5. Copiloto de IA (Módulo de Recomendação)
- **Análise Contextual:** Avalia a carteira atual comparando-a com as metas do usuário e métricas extraídas do mercado.
- **Sugestão de Aportes:** Indica quais ativos ou setores estão sub-representados ou descontados (ex: P/VP atrativo) para orientar o próximo aporte de forma racional.

---

## 📐 Arquitetura da Solução

[ Web Scraping ] ──► [ Banco de Dados ] ◄── [ Interface Web / Dashboard ]
(Status Invest)       (PostgreSQL/SQLite)        (Streamlit / Dash / React)
│
▼
[ Motor de IA / LLM ] ──► [ Recomendações e Relatórios ]


---

## 🗄️ Estrutura Recomendada do Banco de Dados

Para migrar a estrutura da planilha (`Controle`, `Investimentos`, `Renda Fixa`, `Calculadora`, `planilha_automatica`) para um modelo relacional:

```sql
-- Tabela de Lançamentos Financeiros (Fluxo de Caixa)
CREATE TABLE transacoes (
    id SERIAL PRIMARY KEY,
    data DATE NOT NULL,
    tipo VARCHAR(10) CHECK (tipo IN ('ENTRADA', 'SAIDA')),
    categoria VARCHAR(50) NOT NULL, -- Ex: 'Contas', 'Carro', 'Trabalhos'
    descricao TEXT,
    valor NUMERIC(10,2) NOT NULL
);

-- Tabela Cadastral de Ativos
CREATE TABLE ativos (
    ticker VARCHAR(10) PRIMARY KEY, -- Ex: 'MXRF11', 'TAEE3'
    classe VARCHAR(20) NOT NULL,    -- 'FII', 'AÇÃO', 'RENDA_FIXA'
    segmento VARCHAR(30),          -- 'Shopping', 'Papel', 'Eletricidade'
    meta_porcentagem NUMERIC(5,2)  -- Meta de alocação na carteira (%)
);

-- Tabela de Posições do Usuário
CREATE TABLE carteira (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) REFERENCES ativos(ticker),
    quantidade NUMERIC(10,4) NOT NULL,
    preco_medio NUMERIC(10,2) NOT NULL
);

-- Tabela de Indicadores Capturados pelo Scraper
CREATE TABLE cotacoes_mercado (
    ticker VARCHAR(10) REFERENCES ativos(ticker),
    valor_atual NUMERIC(10,2),
    pvp NUMERIC(5,2),
    dividend_yield NUMERIC(5,2),
    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

🧰 Tecnologias Utilizadas

    Linguagem: Python 3.11+

    Coleta de Dados: requests, BeautifulSoup4

    Manipulação de Dados: pandas, openpyxl

    Banco de Dados: SQLite (Desenvolvimento) / PostgreSQL (Produção)

    Visualização/Interface: Streamlit / Plotly

    IA / LLM: API OpenAI / Gemini / LangChain (para geração de pareceres e análises de alocação)

🚀 Roadmap de Desenvolvimento

    [x] Script automatizado de coleta de dados de FIIs sem dependência de driver de navegador.

    [ ] Modelagem e criação do banco de dados relacional.

    [ ] Migração e higienização dos dados legados da planilha Excel.

    [ ] Construção do Dashboard interativo estilo Power BI.

    [ ] Integração da camada de IA com chamadas orientadas a contexto (RAG/Prompt Engineering) para sugestão de aportes.
