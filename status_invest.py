import requests
from bs4 import BeautifulSoup
import openpyxl

# Lista dos FIIs a serem consultados
fundos = [
    'rbfm11', 'bthf11', 'hsml11', 'visc11', 'tvri11',
    'knri11', 'vino11', 'rztr11', 'vghf11', 'mxrf11', 
    'kncr11', 'bcri11', 'hglg11', 'ggrc11', 'mcci11','pvbi11'
]

# Configuração da sessão simulando um navegador real
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://statusinvest.com.br/'
})

def extrair_indicador(soup, termos_busca):
    """
    Busca um indicador considerando:
    1. Atributo 'title' no card contêiner (ex: title="Valor atual do ativo")
    2. Texto interno de tags de título/rótulo (ex: "Valor atual", "DY", "P/VP")
    """
    if isinstance(termos_busca, str):
        termos_busca = [termos_busca]

    # 1. Estratégia A: Buscar por atributo 'title'
    for termo in termos_busca:
        tags_com_title = soup.find_all(lambda t: t.has_attr('title') and termo.lower() in t['title'].lower())
        for tag in tags_com_title:
            valor_tag = tag.find('strong', class_='value') or tag.find('strong')
            if valor_tag:
                val = valor_tag.get_text(strip=True)
                if val and val != '-':
                    return val

    # 2. Estratégia B: Buscar pelo texto do rótulo
    for termo in termos_busca:
        for tag in soup.find_all(['h3', 'span', 'p', 'small', 'b', 'td', 'dt']):
            texto = tag.get_text(strip=True)
            if termo.lower() == texto.lower() or (termo.lower() in texto.lower() and len(texto) <= 20):
                parent = tag
                for _ in range(4):  # Sobe até 4 níveis na árvore HTML
                    parent = parent.parent
                    if not parent:
                        break
                    valor_tag = parent.find('strong', class_='value') or parent.find('strong')
                    if valor_tag:
                        val = valor_tag.get_text(strip=True)
                        if val and val != '-':
                            return val

    return None

def buscar_indicadores(fii):
    url = f'https://statusinvest.com.br/fundos-imobiliarios/{fii.lower()}'
    try:
        response = session.get(url, timeout=12)
        if response.status_code != 200:
            print(f'\033[31mErro {response.status_code} ao acessar {fii.upper()}\033[0m')
            return None, None, None

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extração dos 3 indicadores
        valor_atual_text = extrair_indicador(soup, ['valor atual', 'valor atual do ativo'])
        pvp_text = extrair_indicador(soup, ['p/vp', 'pvp'])
        dy_text = extrair_indicador(soup, ['dividend yield', 'dy'])

        if not valor_atual_text or not pvp_text or not dy_text:
            print(f'\033[33mAviso: Incompleto para {fii.upper()} (Valor: {valor_atual_text} | P/VP: {pvp_text} | DY: {dy_text})\033[0m')

        # Limpeza e conversão dos dados (remove R$, %, substitui vírgula por ponto)
        val_clean = valor_atual_text.replace('R$', '').replace('\xa0', '').replace(',', '.').strip() if valor_atual_text else None
        pvp_clean = pvp_text.replace(',', '.').strip() if pvp_text else None
        dy_clean = dy_text.replace(',', '.').replace('%', '').strip() if dy_text else None

        print(f'\033[32m{fii.upper()} OK -> Valor: R$ {val_clean} | P/VP: {pvp_clean} | DY: {dy_clean}%\033[0m')
        return val_clean, pvp_clean, dy_clean

    except Exception as e:
        print(f'\033[31mErro ao processar {fii.upper()}: {e}\033[0m')
        return None, None, None

# 1. Coleta os dados de todos os fundos
dados_coletados = {}
for fii in fundos:
    val, pvp, dy = buscar_indicadores(fii)
    if val or pvp or dy:
        dados_coletados[fii.upper()] = (val, pvp, dy)

# 2. Atualiza a planilha Excel
caminho_planilha = 'Investimento.xlsx'
wb = openpyxl.load_workbook(caminho_planilha)
dados = wb['planilha_automatica']

for row in dados.iter_rows(min_row=2, max_row=100):
    if row[0].value:
        fii_nome = str(row[0].value).strip().upper()
        if fii_nome in dados_coletados:
            val_atual, pvp_val, dy_val = dados_coletados[fii_nome]
            
            # --- ATRIBUIÇÃO NAS COLUNAS ---
            # row[1] = Coluna B (ex: Valor Atual)
            # row[2] = Coluna C (ex: P/VP)
            # row[3] = Coluna D (ex: Dividend Yield)
            
            if val_atual:
                try:
                    row[1].value = float(val_atual)
                except ValueError:
                    row[1].value = val_atual

            if pvp_val:
                try:
                    row[2].value = float(pvp_val)
                except ValueError:
                    row[2].value = pvp_val

            if dy_val:
                try:
                    row[3].value = float(dy_val)
                except ValueError:
                    row[3].value = dy_val

# 3. Salva as alterações no arquivo
wb.save(caminho_planilha)
print('\n\033[34mPlanilha atualizada e salva com sucesso!\033[0m')