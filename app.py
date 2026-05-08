import streamlit as st
import telebot
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone
import threading
import time

# --- CONFIGURAÇÕES DO BOT ---
TOKEN = '8506261472:AAEFl-coVYJtnVjlILf04n5WJlaMNgqDv84'
bot = telebot.TeleBot(TOKEN)

# --- FUNÇÃO DE HORÁRIO BRASÍLIA ---
def get_now_br():
    # Garante o fuso horário de Brasília/Rio/SP (UTC-3)
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

# --- FUNÇÃO DE FORMATAÇÃO DE DATA ---
def formatar_data_br(valor):
    if not valor or valor in ["Vitalício", "Aguardando", "Aguardando Entrada", "Não Iniciado"]:
        return valor
    try:
        # Tenta converter formatos antigos (ISO) para o padrão BR caso existam no banco
        if "-" in valor and ":" in valor:
            dt = pd.to_datetime(valor, utc=True).tz_convert("America/Sao_Paulo")
            return dt.strftime("%d/%m/%Y %H:%M")
        return valor
    except:
        return valor

def conectar():
    conn = sqlite3.connect('vanthagem_v2.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS membros 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    grupo_id TEXT, grupo_nome TEXT, 
                    user_id TEXT, nome TEXT, username TEXT,
                    entrada TEXT, saida TEXT, 
                    duracao_txt TEXT, status TEXT,
                    invite_link TEXT, telefone TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS historico 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT, nome TEXT, 
                    acao TEXT, grupo_nome TEXT, 
                    data_hora TEXT, detalhes TEXT)''')
    
    # Garantir colunas essenciais
    colunas = [("username", "TEXT"), ("telefone", "TEXT"), ("invite_link", "TEXT")]
    for col, tipo in colunas:
        try: cursor.execute(f"ALTER TABLE membros ADD COLUMN {col} {tipo}")
        except: pass
    
    conn.commit()
    return conn

conn = conectar()

# --- MOTOR DE MONITORAMENTO (FUSO BRASÍLIA) ---
def monitor_geral():
    while True:
        try:
            conn_thread = sqlite3.connect('vanthagem_v2.db')
            cursor = conn_thread.cursor()
            agora = get_now_br()
            
            cursor.execute("SELECT id, grupo_id, user_id, nome, saida, grupo_nome FROM membros WHERE status = 'Ativo'")
            ativos = cursor.fetchall()
            for m in ativos:
                m_id, g_id, u_id, nome, data_saida, g_nome = m
                if data_saida == "Vitalício": continue
                
                try:
                    # Parse da data garantindo o fuso de Brasília para comparação
                    limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M").replace(tzinfo=timezone(timedelta(hours=-3)))
                    if agora >= limite:
                        try:
                            bot.ban_chat_member(g_id, u_id)
                            bot.unban_chat_member(g_id, u_id)
                        except: pass
                        
                        cursor.execute("UPDATE membros SET status = 'Expirado' WHERE id = ?", (m_id,))
                        data_str = agora.strftime("%d/%m/%Y %H:%M")
                        cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                                       (u_id, nome, "Expirou/Saiu", g_nome, data_str, f"Tempo finalizado ({data_saida})"))
                        conn_thread.commit()
                except: continue
            conn_thread.close()
        except: pass
        time.sleep(30)

@bot.chat_member_handler()
def monitorar_entrada(message):
    new_member = message.new_chat_member
    if new_member.status == 'member':
        u_id = str(new_member.user.id)
        g_id = str(message.chat.id)
        conn_in = sqlite3.connect('vanthagem_v2.db')
        cursor = conn_in.cursor()
        cursor.execute("SELECT id, duracao_txt, nome, grupo_nome FROM membros WHERE user_id = ? AND grupo_id = ? AND status = 'Pendente'", (u_id, g_id))
        res = cursor.fetchone()
        if res:
            m_id, duracao, nome, g_nome = res
            agora = get_now_br()
            deltas = {
                "30 minutos": timedelta(minutes=30), "1 hora": timedelta(hours=1),
                "1 semana": timedelta(weeks=1), "15 dias": timedelta(days=15),
                "30 dias": timedelta(days=30), "60 dias": timedelta(days=60),
                "90 dias": timedelta(days=90), "1 ano": timedelta(days=365),
                "2 anos": timedelta(days=730)
            }
            data_entrada = agora.strftime("%d/%m/%Y %H:%M")
            data_saida = (agora + deltas[duracao]).strftime("%d/%m/%Y %H:%M") if duracao != "Vitalício" else "Vitalício"
            
            cursor.execute("UPDATE membros SET entrada = ?, saida = ?, status = 'Ativo' WHERE id = ?", (data_entrada, data_saida, m_id))
            cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                           (u_id, nome, "Entrou", g_nome, data_entrada, f"Plano: {duracao}"))
            conn_in.commit()
        conn_in.close()

if not hasattr(st, "bot_rodando"):
    bot.remove_webhook()
    threading.Thread(target=monitor_geral, daemon=True).start()
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=['chat_member', 'message'], skip_pending=True), daemon=True).start()
    st.bot_rodando = True

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Vanthagem PRO", layout="wide")
# --- SISTEMA DE SEGURANÇA (ADMIN) ---
SENHA_CORRETA = "29072004pP1!"

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "tentativas" not in st.session_state:
    st.session_state.tentativas = 0
if "bloqueado_ate" not in st.session_state:
    st.session_state.bloqueado_ate = None

def login():
    st.markdown("<h1 style='text-align: center;'>🔐 Vanthagem PRO</h1>", unsafe_html=True)
    if st.session_state.bloqueado_ate:
        tempo_restante = st.session_state.bloqueado_ate - datetime.now()
        if tempo_restante.total_seconds() > 0:
            st.error(f"Sistema bloqueado. Tente novamente em {int(tempo_restante.total_seconds() // 60)} minutos.")
            st.stop()
        else:
            st.session_state.bloqueado_ate = None
            st.session_state.tentativas = 0

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            senha_input = st.text_input("Senha Master", type="password")
            if st.form_submit_button("Acessar Sistema", use_container_width=True):
                time.sleep(5) # Proteção de Flood
                if senha_input == SENHA_CORRETA:
                    st.session_state.autenticado = True
                    st.session_state.tentativas = 0
                    st.rerun()
                else:
                    st.session_state.tentativas += 1
                    if st.session_state.tentativas >= 5:
                        st.session_state.bloqueado_ate = datetime.now() + timedelta(minutes=30)
                    st.rerun()

if not st.session_state.autenticado:
    login()
    st.stop()

def sincronizar_dados():
    try:
        cursor_sync = conn.cursor()
        cursor_sync.execute("SELECT DISTINCT grupo_id FROM membros")
        for g in cursor_sync.fetchall():
            try:
                chat = bot.get_chat(g[0])
                cursor_sync.execute("UPDATE membros SET grupo_nome = ? WHERE grupo_id = ?", (chat.title, g[0]))
            except: pass
        cursor_sync.execute("SELECT DISTINCT user_id FROM membros")
        for u in cursor_sync.fetchall():
            try:
                user = bot.get_chat(str(u[0]).strip())
                u_nome = f"{user.first_name} {user.last_name or ''}".strip()
                u_username = f"@{user.username}" if user.username else "Sem Username"
                cursor_sync.execute("UPDATE membros SET nome = ?, username = ? WHERE user_id = ?", (u_nome, u_username, u[0]))
            except: 
                pass
        conn.commit()
        return True
    except: return False

st.sidebar.title("💎 Vanthagem PRO")
if st.sidebar.button("🔄 Sincronizar Tudo"):
    if sincronizar_dados(): st.sidebar.success("Atualizado!")

aba = st.sidebar.radio("Navegação", ["📊 Dashboard Geral", "➕ Novo Cliente", "⚙️ Gerenciar Tempo", "📜 Expirados", "👤 Perfil do Cliente"])

def verificar_urgencia(data_str):
    if data_str in ["Vitalício", "Aguardando Entrada", "Aguardando", "Não Iniciado"]: return False
    try:
        data_fim = datetime.strptime(data_str, "%d/%m/%Y %H:%M").replace(tzinfo=timezone(timedelta(hours=-3)))
        diff = data_fim - get_now_br()
        return diff.total_seconds() < 86400 and diff.total_seconds() > 0
    except: return False

if aba == "📊 Dashboard Geral":
    st.title("📊 Gestão de Membros Ativos")
    df = pd.read_sql_query("SELECT id, grupo_nome, nome, username, status, entrada, saida, invite_link FROM membros WHERE status IN ('Ativo', 'Pendente')", conn)
    
    if not df.empty:
        df['entrada'] = df['entrada'].apply(formatar_data_br)
        df['saida'] = df['saida'].apply(formatar_data_br)
        df['critico'] = df['saida'].apply(verificar_urgencia)
        
        st.sidebar.subheader("Filtros")
        f_grupo = st.sidebar.selectbox("Filtrar por Grupo", options=["Todos"] + list(df['grupo_nome'].unique()))
        apenas_criticos = st.sidebar.checkbox("Mostrar apenas Críticos (<24h)")
        
        dff = df.copy()
        if f_grupo != "Todos": dff = dff[dff['grupo_nome'] == f_grupo]
        if apenas_criticos: dff = dff[dff['critico'] == True]

        def highlight_critico(row):
            return ['background-color: #ff4b4b; color: white' if row.critico and row.status == 'Ativo' else '' for _ in row]

        st.dataframe(dff.style.apply(highlight_critico, axis=1), column_order=['grupo_nome', 'nome', 'username', 'status', 'entrada', 'saida'], width='stretch')
        
        # --- RECURSO: RECUPERAÇÃO DE LINKS COM SELETOR ---
        st.subheader("🔗 Recuperação de Links de Convite")
        pendentes = dff[dff['status'] == 'Pendente']
        if not pendentes.empty:
            lista_pendentes = [f"{p['nome']} ({p['grupo_nome']})" for _, p in pendentes.iterrows()]
            selecionado = st.selectbox("Selecione o membro pendente para recuperar o link:", lista_pendentes)
            
            # Localiza o link do membro selecionado
            index_sel = lista_pendentes.index(selecionado)
            p_sel = pendentes.iloc[index_sel]
            
            st.info(f"Link para **{p_sel['nome']}** no grupo **{p_sel['grupo_nome']}**:")
            st.code(p_sel['invite_link'])
        else:
            st.write("Nenhum usuário aguardando entrada no momento.")
    else: st.info("Nenhum membro ativo ou pendente encontrado.")

elif aba == "➕ Novo Cliente":
    st.title("➕ Gerar Acesso Inteligente")
    if 'g_valido' not in st.session_state: st.session_state.g_valido = ""
    if 'u_valido' not in st.session_state: st.session_state.u_valido = ""
    if 'user_valido' not in st.session_state: st.session_state.user_valido = ""

    with st.container(border=True):
        colA, colB = st.columns(2)
        with colA:
            g_id_in = str(st.text_input("ID do Grupo (-100...)")).strip()
            if st.button("🔍 Validar Grupo"):
                try: 
                    chat = bot.get_chat(str(g_id_in).strip()); st.session_state.g_valido = chat.title
                    st.success(f"Grupo: {chat.title}")
                except: st.error("Grupo não encontrado.")
        with colB:
            u_id_in = str(st.text_input("ID do Usuário")).strip()
            if st.button("👤 Validar Usuário"):
                try:
                    u = bot.get_chat(str(u_id_in).strip())
                    st.session_state.u_valido = f"{u.first_name} {u.last_name or ''}".strip()
                    st.session_state.user_valido = f"@{u.username}" if u.username else "Sem Username"
                    st.success(f"Usuário: {st.session_state.u_valido}")
                except Exception as e: st.error(f"Usuário não encontrado. Erro: {e}")

    with st.form("cadastro"):
        st.subheader("Confirmar Cadastro")
        c1, c2 = st.columns(2)
        final_gnome = c1.text_input("Grupo Selecionado", value=st.session_state.g_valido, disabled=True)
        final_unome = c2.text_input("Nome do Cliente", value=st.session_state.u_valido)
        final_user = c1.text_input("Username (@)", value=st.session_state.user_valido)
        final_tel = c2.text_input("Telefone (Opcional)")
        tempo = st.selectbox("Duração", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        
        if st.form_submit_button("GERAR ACESSO"):
            if not final_gnome or not final_unome: st.error("Valide os IDs primeiro!")
            else:
                try:
                    link = bot.create_chat_invite_link(g_id_in, member_limit=1).invite_link
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, username, entrada, saida, duracao_txt, status, invite_link, telefone) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                   (g_id_in, final_gnome, u_id_in, final_unome, final_user, "Aguardando", "Aguardando", tempo, "Pendente", link, final_tel))
                    cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                                   (u_id_in, final_unome, "Link Gerado", final_gnome, get_now_br().strftime("%d/%m/%Y %H:%M"), f"Plano: {tempo}"))
                    conn.commit()
                    st.success("✅ Link Gerado!"); st.code(link)
                except: st.error("Erro ao criar link. Verifique as permissões do Bot.")

elif aba == "⚙️ Gerenciar Tempo":
    st.title("⚙️ Gerenciamento e Renovação")
    # ALTERAÇÃO: Filtrando apenas membros ATIVOS para renovação
    df_g = pd.read_sql_query("SELECT DISTINCT grupo_nome FROM membros WHERE status = 'Ativo'", conn)
    f_g_tempo = st.selectbox("1. Filtrar por Grupo:", ["Todos"] + list(df_g['grupo_nome'].unique()))
    
    query_tempo = "SELECT id, user_id, nome, saida, grupo_nome FROM membros WHERE status = 'Ativo'"
    params = []
    if f_g_tempo != "Todos":
        query_tempo += " AND grupo_nome = ?"
        params.append(f_g_tempo)
    
    df_m = pd.read_sql_query(query_tempo, conn, params=params)
    
    if not df_m.empty:
        escolha = st.selectbox("2. Escolha o Cliente Ativo:", [f"{r['nome']} ({r['grupo_nome']})" for _, r in df_m.iterrows()])
        cliente_idx = [f"{r['nome']} ({r['grupo_nome']})" for _, r in df_m.iterrows()].index(escolha)
        m_data = df_m.iloc[cliente_idx]
        
        st.info(f"Expiração Atual: {m_data['saida']}")
        add_t = st.radio("Adicionar Tempo:", ["30 min", "1 hora", "1 dia", "15 dias", "30 dias", "60 dias", "📅 Data Personalizada"])

        data_personalizada = None
        if add_t == "📅 Data Personalizada":
            data_personalizada = st.date_input("Escolha a nova data de expiração")
            hora_personalizada = st.time_input("Escolha o horário")
        
        if st.button("CONFIRMAR RENOVAÇÃO"):
            base = datetime.strptime(m_data['saida'], "%d/%m/%Y %H:%M").replace(tzinfo=timezone(timedelta(hours=-3)))

            deltas = {
                "30 min": timedelta(minutes=30),
                "1 hora": timedelta(hours=1),
                "1 dia": timedelta(days=1),
                "15 dias": timedelta(days=15),
                "30 dias": timedelta(days=30),
                "60 dias": timedelta(days=60)
            }

            if add_t == "📅 Data Personalizada":
                dt_personalizada = datetime.combine(data_personalizada, hora_personalizada)
                nova_data = dt_personalizada.strftime("%d/%m/%Y %H:%M")
            else:
                nova_data = (base + deltas[add_t]).strftime("%d/%m/%Y %H:%M")
            
            cursor = conn.cursor()
            cursor.execute("UPDATE membros SET saida = ?, status = 'Ativo' WHERE id = ?", (nova_data, int(m_data['id'])))
            cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                           (m_data['user_id'], m_data['nome'], "Renovação", m_data['grupo_nome'], get_now_br().strftime("%d/%m/%Y %H:%M"), f"Até {nova_data}"))
            conn.commit()
            st.success(f"✅ Tempo adicionado com sucesso!"); st.balloons()
    else: st.info("Não há membros ativos para gerenciar neste filtro.")

elif aba == "📜 Expirados":
    st.title("📜 Histórico de Expirados")
    df_grupos_exp = pd.read_sql_query("SELECT DISTINCT grupo_nome FROM membros WHERE status = 'Expirado'", conn)
    f_g_exp = st.selectbox("Filtrar Grupo:", ["Todos"] + list(df_grupos_exp['grupo_nome'].unique()))
    
    query_exp = "SELECT grupo_nome, nome, username, entrada, saida FROM membros WHERE status = 'Expirado'"
    if f_g_exp != "Todos": query_exp += f" AND grupo_nome = '{f_g_exp}'"
    
    df_exp = pd.read_sql_query(query_exp + " ORDER BY id DESC", conn)
    
    if not df_exp.empty:

        if st.button("🗑️ Excluir Todo Histórico de Expirados"):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM membros WHERE status = 'Expirado'")
            conn.commit()
            st.success("Histórico apagado com sucesso!")
            st.rerun()

        # Limpeza de strings para visualização profissional
        df_exp.replace("Aguardando Entrada", "Não Iniciado", inplace=True)
        df_exp.replace("Aguardando", "Não Iniciado", inplace=True)
        st.dataframe(df_exp, width='stretch')
    else: st.info("Nenhum histórico de membros expirados.")

elif aba == "👤 Perfil do Cliente":
    st.title("👤 Dossiê do Cliente")
    df_g = pd.read_sql_query("SELECT DISTINCT grupo_nome FROM membros", conn)
    f_g_p = st.selectbox("Filtrar por Grupo:", ["Todos"] + list(df_g['grupo_nome'].unique()))
    
    query_p = "SELECT DISTINCT user_id, nome FROM membros"
    if f_g_p != "Todos": query_p += f" WHERE grupo_nome = '{f_g_p}'"
    
    df_u = pd.read_sql_query(query_p, conn)
    if not df_u.empty:
        cliente = st.selectbox("Escolha o Cliente:", df_u['nome'])
        uid = df_u[df_u['nome'] == cliente]['user_id'].values[0]
        dados = pd.read_sql_query("SELECT * FROM membros WHERE user_id = ?", conn, params=(uid,))
        
        with st.container(border=True):
            st.subheader(f"Ficha: {cliente}")
            c1, c2 = st.columns(2)
            c1.write(f"**Username:** {dados['username'].iloc[0]}")
            c1.write(f"**ID:** {uid}")
            c2.write(f"**Telefone:** {dados['telefone'].iloc[0] or 'Não informado'}")
            
            st.write("**Acessos Atuais/Passados:**")
            for _, r in dados.iterrows():
                cor = "🟢" if r['status'] == 'Ativo' else ("🟡" if r['status'] == 'Pendente' else "🔴")
                st.write(f"{cor} {r['grupo_nome']} | Expiração: {formatar_data_br(r['saida'])}")

        st.subheader("📑 Linha do Tempo")
        hist = pd.read_sql_query("SELECT data_hora, acao, grupo_nome, detalhes FROM historico WHERE user_id = ? ORDER BY id DESC", conn, params=(uid,))
        st.dataframe(hist, width='stretch')
    else: st.info("Nenhum cliente cadastrado.")
