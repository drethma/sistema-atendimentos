import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
import hashlib
from fpdf import FPDF

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Gestão de Atendimentos", 
    page_icon="💼", 
    layout="wide"
)

# --- ESTILIZAÇÃO (CSS CORRIGIDO) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap');
    
    html, body, h1, h2, h3, h4, h5, h6, p, li, ol, .stButton button, .stTextInput, .stSelectbox {
        font-family: 'Open Sans', sans-serif !important;
    }
    
    [data-testid="stMetricValue"] {
        font-weight: 700;
        color: #4da6ff;
    }
    
    .stButton button {
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNÇÕES DE SEGURANÇA (HASH) ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return True
    return False

# --- BANCO DE DADOS (SQLite) ---
def init_db():
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios 
                 (username TEXT PRIMARY KEY, password TEXT, tipo TEXT)''')
    c.execute('SELECT count(*) FROM usuarios')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO usuarios VALUES (?, ?, ?)', ('admin', make_hashes('admin123'), 'admin'))
    c.execute('''CREATE TABLE IF NOT EXISTS funcoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor_hora REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS atendimentos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, inicio TEXT, termino TEXT, 
                  funcao TEXT, valor_total REAL, usuario_responsavel TEXT)''')
    conn.commit()
    conn.close()
    atualizar_banco_legado()

def atualizar_banco_legado():
    conn = sqlite3.connect('atendimentos.db')
    try:
        pd.read_sql('SELECT usuario_responsavel FROM atendimentos LIMIT 1', conn)
    except:
        c = conn.cursor()
        try:
            c.execute('ALTER TABLE atendimentos ADD COLUMN usuario_responsavel TEXT')
            conn.commit()
        except: pass
    finally:
        conn.close()

# --- CLASSE PARA GERAR O PDF ---
class PDF(FPDF):
    def header(self):
        self.set_fill_color(77, 166, 255)
        self.rect(0, 0, 297, 25, 'F')
        self.set_font('Arial', 'B', 15)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, 'Relatório de Atendimentos', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Pagina {self.page_no()}' + ' - Sistema de Gestão', 0, 0, 'C')

def criar_pdf_relatorio(df, mes_nome, ano, metricas, usuario, filtro_funcao):
    pdf = PDF('L', 'mm', 'A4')
    pdf.add_page()
    
    # --- BLOCO DE RESUMO ---
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(0, 0, 0)
    
    subtitulo = f'Periodo: {mes_nome} / {ano} - Usuario Solicitante: {usuario}'
    if filtro_funcao != 'Todas':
        subtitulo += f' - Filtro Funcao: {filtro_funcao}'
        
    pdf.cell(0, 10, subtitulo, 0, 1, 'L')
    
    pdf.set_fill_color(240, 240, 240)
    pdf.rect(10, 35, 277, 20, 'F')
    
    pdf.set_y(40)
    pdf.set_font('Arial', '', 11)
    texto_resumo = f"     Faturamento: R$ {metricas['valor']:,.2f}          Horas Trabalhadas: {metricas['horas']:.1f} h          Atendimentos: {metricas['qtd']}"
    pdf.cell(0, 10, texto_resumo, 0, 1, 'C')
    
    pdf.ln(15)

    # --- TABELA DE DADOS ---
    col_widths = [15, 45, 45, 80, 40, 50] 
    headers = ['ID', 'Inicio', 'Termino', 'Funcao', 'Valor Total', 'Responsavel']
    
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(200, 220, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 10, h, 1, 0, 'C', 1)
    pdf.ln()
    
    pdf.set_font('Arial', '', 9)
    fill = False
    
    for index, row in df.iterrows():
        def clean(txt):
            return str(txt).encode('latin-1', 'replace').decode('latin-1')

        pdf.set_fill_color(245, 245, 245)
        pdf.cell(col_widths[0], 8, str(row['id']), 1, 0, 'C', fill)
        pdf.cell(col_widths[1], 8, str(row['inicio']), 1, 0, 'C', fill)
        pdf.cell(col_widths[2], 8, str(row['termino']), 1, 0, 'C', fill)
        pdf.cell(col_widths[3], 8, clean(row['funcao']), 1, 0, 'L', fill)
        pdf.cell(col_widths[4], 8, f"R$ {row['valor_total']:,.2f}", 1, 0, 'R', fill)
        pdf.cell(col_widths[5], 8, clean(row['usuario_responsavel']), 1, 0, 'L', fill)
        pdf.ln()
        fill = not fill
        
    return pdf.output(dest='S').encode('latin-1')

# --- FUNÇÕES CRUD E LÓGICA ---
def login_user(username, password):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username = ?', (username,))
    data = c.fetchall()
    conn.close()
    if data and check_hashes(password, data[0][1]):
        return data[0][2]
    return False

def criar_usuario(username, password, tipo):
    try:
        conn = sqlite3.connect('atendimentos.db')
        c = conn.cursor()
        c.execute('INSERT INTO usuarios VALUES (?, ?, ?)', (username, make_hashes(password), tipo))
        conn.commit()
        conn.close()
        return True
    except: return False

def listar_usuarios():
    conn = sqlite3.connect('atendimentos.db')
    df = pd.read_sql('SELECT username, tipo FROM usuarios', conn)
    conn.close()
    return df

def excluir_usuario(username):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('DELETE FROM usuarios WHERE username = ?', (username,))
    conn.commit()
    conn.close()

def carregar_funcoes():
    conn = sqlite3.connect('atendimentos.db')
    df = pd.read_sql('SELECT * FROM funcoes', conn)
    conn.close()
    return df

def salvar_funcao(nome, valor):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('INSERT INTO funcoes (nome, valor_hora) VALUES (?, ?)', (nome, valor))
    conn.commit()
    conn.close()

def salvar_atendimento(inicio, termino, funcao, valor_total, usuario):
    conn = sqlite3.connect('atendimentos.db')
    c = conn.cursor()
    c.execute('INSERT INTO atendimentos (inicio, termino, funcao, valor_total, usuario_responsavel) VALUES (?, ?, ?, ?, ?)', 
              (inicio, termino, funcao, valor_total, usuario))
    conn.commit()
    conn.close()

def carregar_atendimentos():
    conn = sqlite3.connect('atendimentos.db')
    if st.session_state.get('tipo') == 'admin':
        query = 'SELECT * FROM atendimentos'
        params = ()
    else:
        query = 'SELECT * FROM atendimentos WHERE usuario_responsavel = ?'
        params = (st.session_state.get('usuario'),)
        
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    if not df.empty:
        df['inicio'] = pd.to_datetime(df['inicio'])
        df['termino'] = pd.to_datetime(df['termino'])
        # Correção para garantir que valores antigos vazios virem "N/A"
        if 'usuario_responsavel' not in df.columns:
            df['usuario_responsavel'] = 'N/A'
        else:
            df['usuario_responsavel'] = df['usuario_responsavel'].fillna('N/A')
            
    return df

# Inicializa DB
init_db()

# --- GESTÃO DE SESSÃO ---
if 'logado' not in st.session_state:
    st.session_state.update({'logado': False, 'usuario': None, 'tipo': None})

# --- TELA DE LOGIN ---
if not st.session_state['logado']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.title("🔐 Acesso Restrito")
        st.markdown("Bem-vindo ao sistema de **Gestão de Atendimentos**.")
        with st.form("login_form"):
            usuario = st.text_input("👤 Usuário")
            senha = st.text_input("🔑 Senha", type="password")
            if st.form_submit_button("🚀 Entrar no Sistema"):
                tipo = login_user(usuario, senha)
                if tipo:
                    st.session_state.update({'logado': True, 'usuario': usuario, 'tipo': tipo})
                    st.rerun()
                else: st.error("Acesso negado.")

# --- SISTEMA PRINCIPAL ---
else:
    st.sidebar.title("Menu")
    st.sidebar.markdown(f"👤 **{st.session_state['usuario']}**")
    st.sidebar.caption(f"Acesso: {st.session_state['tipo'].upper()}")
    
    opcoes_menu = {
        "Funções": "🛠️ Cadastro Função",
        "Atendimento": "📝 Novo Atendimento",
        "Relatorios": "📊 Relatórios",
        "Admin": "⚙️ Administração"
    }
    
    lista_menu = [opcoes_menu["Funções"], opcoes_menu["Atendimento"], opcoes_menu["Relatorios"]]
    if st.session_state['tipo'] == 'admin':
        lista_menu.append(opcoes_menu["Admin"])
        
    menu = st.sidebar.radio("Navegue por aqui:", lista_menu)
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Sair / Logout"):
        st.session_state.update({'logado': False, 'usuario': None, 'tipo': None})
        st.rerun()

    # --- TELA 01: FUNÇÕES ---
    if menu == opcoes_menu["Funções"]:
        st.title("🛠️ Cadastro de Funções")
        st.markdown("Defina os valores por hora para cada tipo de serviço.")
        with st.container(border=True):
            with st.form("form_funcao", clear_on_submit=True):
                c1, c2 = st.columns([2, 1])
                nome = c1.text_input("Nome do Cargo/Função")
                valor = c2.number_input("Valor Hora (R$)", min_value=0.0, format="%.2f")
                if st.form_submit_button("💾 Salvar Função"):
                    if nome and valor > 0:
                        salvar_funcao(nome, valor)
                        st.success(f"✅ '{nome}' cadastrado!")
        st.subheader("📋 Funções Ativas")
        df = carregar_funcoes()
        if not df.empty: st.dataframe(df, hide_index=True, use_container_width=True)

    # --- TELA 02: ATENDIMENTO ---
    elif menu == opcoes_menu["Atendimento"]:
        st.title("📝 Registrar Atendimento")
        df_func = carregar_funcoes()
        if df_func.empty:
            st.warning("⚠️ Nenhuma função cadastrada.")
        else:
            with st.container(border=True):
                with st.form("form_atend", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    d_ini = c1.date_input("📅 Data Início")
                    h_ini = c1.time_input("⏰ Hora Início")
                    d_fim = c2.date_input("📅 Data Término")
                    h_fim = c2.time_input("⏰ Hora Término")
                    func = st.selectbox("💼 Selecione a Função", df_func['nome'].tolist())
                    if st.form_submit_button("✅ Calcular e Salvar"):
                        dt_ini = datetime.combine(d_ini, h_ini)
                        dt_fim = datetime.combine(d_fim, h_fim)
                        if dt_fim <= dt_ini:
                            st.error("❌ Erro: Término deve ser depois do início.")
                        else:
                            duracao = (dt_fim - dt_ini).total_seconds() / 3600
                            val_h = df_func.loc[df_func['nome'] == func, 'valor_hora'].values[0]
                            total = duracao * val_h
                            salvar_atendimento(dt_ini, dt_fim, func, total, st.session_state['usuario'])
                            st.success(f"✅ Salvo! Total: **R$ {total:,.2f}**")

    # --- TELA 03: RELATÓRIOS ---
    elif menu == opcoes_menu["Relatorios"]:
        st.title("📊 Relatórios Gerenciais")
        if st.session_state['tipo'] != 'admin':
            st.info(f"🔒 Dados filtrados para: **{st.session_state['usuario']}**")
        else:
            st.success("🔓 Modo Admin: Visualizando TUDO.")
            
        df = carregar_atendimentos()
        if not df.empty:
            anos = sorted(df['inicio'].dt.year.unique())
            meses_dict = {1:"Janeiro", 2:"Fevereiro", 3:"Marco", 4:"Abril", 5:"Maio", 6:"Junho",
                          7:"Julho", 8:"Agosto", 9:"Setembro", 10:"Outubro", 11:"Novembro", 12:"Dezembro"}
            
            with st.container(border=True):
                # --- LAYOUT DOS FILTROS ---
                # Se for ADMIN, usamos 4 colunas. Se não, 3.
                if st.session_state['tipo'] == 'admin':
                    c1, c2, c3, c4 = st.columns(4)
                else:
                    c1, c2, c3 = st.columns(3)
                    c4 = None # Placeholder

                f_ano = c1.selectbox("📅 Ano", anos, index=len(anos)-1)
                f_mes = c2.selectbox("🗓️ Mês", range(1,13), format_func=lambda x: meses_dict[x], index=datetime.now().month-1)
                
                opcoes_funcoes = ['Todas'] + sorted(df['funcao'].unique().tolist())
                f_funcao = c3.selectbox("💼 Função", opcoes_funcoes)

                # FILTRO DE USUÁRIO (APENAS PARA ADMIN)
                f_usuario = 'Todos'
                if st.session_state['tipo'] == 'admin':
                    # Pega todos os usuários únicos que têm registros
                    lista_users = ['Todos'] + sorted(df['usuario_responsavel'].astype(str).unique().tolist())
                    f_usuario = c4.selectbox("👤 Usuário", lista_users)

            # --- APLICAÇÃO DOS FILTROS ---
            df_fil = df[(df['inicio'].dt.year == f_ano) & (df['inicio'].dt.month == f_mes)]
            
            if f_funcao != 'Todas':
                df_fil = df_fil[df_fil['funcao'] == f_funcao]
            
            # Aplica filtro de usuário se Admin selecionou alguém específico
            if st.session_state['tipo'] == 'admin' and f_usuario != 'Todos':
                df_fil = df_fil[df_fil['usuario_responsavel'] == f_usuario]
            
            if not df_fil.empty:
                # Métricas
                total_val = df_fil['valor_total'].sum()
                total_horas = (df_fil['termino']-df_fil['inicio']).dt.total_seconds().sum()/3600
                total_qtd = len(df_fil)
                metricas = {'valor': total_val, 'horas': total_horas, 'qtd': total_qtd}

                st.markdown(f"### 📈 Resumo: {meses_dict[f_mes]} / {f_ano}")
                k1, k2, k3 = st.columns(3)
                k1.metric("💰 Faturamento", f"R$ {total_val:,.2f}")
                k2.metric("⏱️ Horas Totais", f"{total_horas:.1f} h")
                k3.metric("📂 Atendimentos", total_qtd)
                st.divider()
                
                # Visualização Tabela
                df_show = df_fil.copy()
                df_show['inicio'] = df_show['inicio'].dt.strftime('%d/%m/%Y %H:%M')
                df_show['termino'] = df_show['termino'].dt.strftime('%d/%m/%Y %H:%M')
                
                df_display = df_show.copy()
                df_display['valor_total'] = df_display['valor_total'].apply(lambda x: f"R$ {x:,.2f}")
                df_display = df_display[['id', 'inicio', 'termino', 'funcao', 'valor_total', 'usuario_responsavel']]
                df_display.columns = ['ID', 'Início', 'Término', 'Função', 'Valor Total', 'Responsável']
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                
                # Downloads
                col_d1, col_d2 = st.columns(2)
                buffer_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_excel, engine='xlsxwriter') as writer:
                    df_fil.to_excel(writer, index=False)
                col_d1.download_button("📥 Baixar Planilha Excel", buffer_excel.getvalue(), 
                                     f"Relatorio_{meses_dict[f_mes]}_{f_ano}.xlsx", use_container_width=True)
                
                pdf_bytes = criar_pdf_relatorio(df_show, meses_dict[f_mes], f_ano, metricas, st.session_state['usuario'], f_funcao)
                col_d2.download_button("📄 Baixar Relatório PDF", pdf_bytes, 
                                     f"Relatorio_{meses_dict[f_mes]}_{f_ano}.pdf", mime='application/pdf', use_container_width=True)
            else: st.info(f"Sem dados para os filtros selecionados.")
        else: st.info("📭 Nenhum dado registrado ainda.")

    # --- TELA 04: ADMIN ---
    elif menu == opcoes_menu["Admin"]:
        st.title("⚙️ Administração de Usuários")
        with st.expander("➕ Adicionar Novo Usuário", expanded=True):
            with st.form("new_user"):
                u = st.text_input("Novo Login")
                p = st.text_input("Senha", type="password")
                t = st.selectbox("Nível", ["comum", "admin"])
                if st.form_submit_button("Criar Usuário"):
                    if u and p: 
                        if criar_usuario(u, p, t): st.success("✅ Criado!")
                        else: st.error("❌ Usuário já existe.")
        st.subheader("👥 Usuários Cadastrados")
        df_users = listar_usuarios()
        for i, row in df_users.iterrows():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"👤 **{row['username']}**")
            c2.caption(f"Tipo: {row['tipo']}")
            if row['username'] != 'admin':
                if c3.button("🗑️ Excluir", key=f"del_{row['username']}"):
                    excluir_usuario(row['username'])
                    st.rerun()