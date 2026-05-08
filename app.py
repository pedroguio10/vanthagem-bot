import streamlit as st
import telebot
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone
import threading
import time

# --- CONFIGURAÇÕES DA PÁGINA (DEVE SER O PRIMEIRO COMANDO STREAMLIT) ---
st.set_page_config(page_title="Vanthagem PRO", layout="wide")

# --- SISTEMA DE SEGURANÇA (ADMIN) ---
SENHA_CORRETA = "29072004pP1!"

# Inicializa os estados de controle se não existirem
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "tentativas" not in st.session_state:
    st.session_state.tentativas = 0
if "bloqueado_ate" not in st.session_state:
    st.session_state.bloqueado_ate = None

def login():
    st.markdown("<h1 style='text-align: center;'>🔐 Vanthagem PRO</h1>", unsafe_html=True)
    st.markdown("<p style='text-align: center;'>Acesso restrito ao administrador</p>", unsafe_html=True)
    
    # Verifica bloqueio de 30 minutos
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
            senha_input = st.text_input("Digite a Senha Master", type="password")
            entrar = st.form_submit_button("Acessar Sistema", use_container_width=True)
            
            if entrar:
                time.sleep(5) # Proteção de Flood (5 segundos)
                if senha_input == SENHA_CORRETA:
                    st.session_state.autenticado = True
                    st.session_state.tentativas = 0
                    st.rerun()
                else:
                    st.session_state.tentativas += 1
                    if st.session_state.tentativas >= 5:
                        st.session_state.bloqueado_ate = datetime.now() + timedelta(minutes=30)
                        st.error("Muitas tentativas! Bloqueado por 30 minutos.")
                    else:
                        st.warning(f"Senha incorreta! Tentativa {st.session_state.tentativas} de 5.")
                st.rerun()

# Executa a trava de segurança
if not st.session_state.autenticado:
    login()
    st.stop()

# =========================================================================
# --- DAQUI PARA BAIXO: SEU CÓDIGO ORIGINAL (ZERO MUDANÇAS) ---
# =========================================================================

# --- CONFIGURAÇÕES DO BOT ---
TOKEN = '8506261472:AAEFl-coVYJtnVjlILf04n5WJlaMNgqDv84'
bot = telebot.TeleBot(TOKEN)

# --- FUNÇÃO DE HORÁRIO BRASÍLIA ---
def get_now_br():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

# --- FUNÇÃO DE FORMATAÇÃO DE DATA ---
def formatar_data_br(valor):
    if not valor or valor in ["Vitalício", "Aguardando", "Aguardando Entrada", "Não Iniciado"]:
        return valor
    try:
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
                    user_id TEXT, nome TEXT, acao TEXT,
                    grupo_nome TEXT, data_hora TEXT, detalhes TEXT)''')
    conn.commit()
    return conn

conn = conectar()

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
                    limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M").replace(tzinfo=timezone(timedelta(hours=-3)))
                    if agora >= limite:
                        try:
                            bot.ban_chat_member(int(g_id), int(u_id))
                            bot.unban_chat_member(int(g_id), int(u_id))
                        except: pass
                        cursor.execute("UPDATE membros SET status = 'Expirado' WHERE id = ?", (m_id,))
                        cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                                       (u_id, nome, "Expirou", g_nome, agora.strftime("%d/%m/%Y %H:%M"), "Removido automaticamente"))
                        conn_thread.commit()
                except: continue
            conn_thread.close()
        except Exception as e: print(f"Erro monitor: {e}")
        time.sleep(30)

@bot.chat_member_handler()
def monitorar_entrada(message):
    new_member = message.new_chat_member
    if new_member.status == 'member':
        u_id, g_id = str(new_member.user.id), str(message.chat.id)
        conn_in = sqlite3.connect('vanthagem_v2.db')
        cursor = conn_in.cursor()
        cursor.execute("SELECT id, duracao_txt, nome, grupo_nome FROM membros WHERE user_id = ? AND grupo_id = ? AND status = 'Pendente'", (u_id, g_id))
        res = cursor.fetchone()
        if res:
            m_id, duracao, nome, g_nome = res
            agora = get_now_br()
            deltas = {"30 minutos": timedelta(minutes=30), "1 hora": timedelta(hours=1), "1 semana": timedelta(weeks=1), "15 dias": timedelta(days=15), "30 dias": timedelta(days=30), "60 dias": timedelta(days=60), "90 dias": timedelta(days=90), "1 ano": timedelta(days=365), "2 anos": timedelta(days=730)}
            data_entrada = agora.strftime("%d/%m/%Y %H:%M")
            data_saida = "Vitalício" if duracao == "Vitalício" else (agora + deltas[duracao]).strftime("%d/%m/%Y %H:%M")
            cursor.execute("UPDATE membros SET entrada = ?, saida = ?, status = 'Ativo' WHERE id = ?", (data_entrada, data_saida, m_id))
            cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                           (u_id, nome, "Entrou", g_nome, data_entrada, f"Plano {duracao}"))
            conn_in.commit()
        conn_in.close()

if not hasattr(st, "bot_rodando"):
    bot.remove_webhook()
    threading.Thread(target=monitor_geral, daemon=True).start()
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=['chat_member'], skip_pending=True), daemon=True).start()
    st.bot_rodando = True

st.sidebar.title("💎 Vanthagem PRO")
aba = st.sidebar.radio("Navegação", ["📊 Dashboard Geral", "➕ Novo Cliente", "⚙️ Gerenciar Tempo", "👤 Perfil do Cliente", "📜 Expirados"])

if aba == "📊 Dashboard Geral":
    st.title("📊 Gestão de Membros")
    df = pd.read_sql_query("SELECT grupo_nome, nome, username, status, entrada, saida FROM membros WHERE status IN ('Ativo', 'Pendente')", conn)
    if not df.empty:
        df['entrada'] = df['entrada'].apply(formatar_data_br)
        df['saida'] = df['saida'].apply(formatar_data_br)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.info("Nenhum membro ativo ou pendente no momento.")

elif aba == "➕ Novo Cliente":
    st.title("➕ Cadastrar Novo Acesso")
    with st.form("cadastro"):
        c1, c2 = st.columns(2)
        g_id, u_id = c1.text_input("ID do Grupo (-100...)"), c1.text_input("ID do Usuário")
        g_nome, u_nome = c2.text_input("Nome do Grupo"), c2.text_input("Nome do Cliente")
        tempo = st.selectbox("Duração do Acesso", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        if st.form_submit_button("GERAR LINK E SALVAR"):
            try:
                link = bot.create_chat_invite_link(int(g_id), member_limit=1).invite_link
                conn.cursor().execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida, duracao_txt, status, invite_link) VALUES (?,?,?,?,?,?,?,?,?)",
                               (g_id, g_nome, u_id, u_nome, "Aguardando", "Aguardando", tempo, "Pendente", link))
                conn.commit()
                st.success("✅ Link Gerado com Sucesso!"); st.code(link)
            except Exception as e: st.error(f"Erro ao gerar link: {e}")

elif aba == "⚙️ Gerenciar Tempo":
    st.title("⚙️ Gerenciar Permanência")
    df_ativos = pd.read_sql_query("SELECT id, nome, grupo_nome, saida FROM membros WHERE status = 'Ativo'", conn)
    if not df_ativos.empty:
        cliente_escolhido = st.selectbox("Selecione o Cliente:", df_ativos['nome'] + " - " + df_ativos['grupo_nome'])
        m_id = int(df_ativos[df_ativos['nome'] + " - " + df_ativos['grupo_nome'] == cliente_escolhido]['id'].values[0])
        st.subheader("Ações Rápidas")
        c1, c2 = st.columns(2)
        if c1.button("Remover Imediatamente"):
            try:
                g_id = pd.read_sql_query(f"SELECT grupo_id FROM membros WHERE id={m_id}", conn)['grupo_id'].iloc[0]
                u_id = pd.read_sql_query(f"SELECT user_id FROM membros WHERE id={m_id}", conn)['user_id'].iloc[0]
                bot.ban_chat_member(int(g_id), int(u_id)); bot.unban_chat_member(int(g_id), int(u_id))
                conn.cursor().execute("UPDATE membros SET status = 'Removido Man.' WHERE id = ?", (m_id,))
                conn.commit(); st.success("Membro removido."); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")
        if c2.button("Tornar Vitalício"):
            conn.cursor().execute("UPDATE membros SET saida = 'Vitalício', duracao_txt = 'Vitalício' WHERE id = ?", (m_id,))
            conn.commit(); st.success("Membro agora é Vitalício."); st.rerun()
    else: st.info("Nenhum membro ativo para gerenciar.")

elif aba == "👤 Perfil do Cliente":
    st.title("👤 Perfil Detalhado")
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
                st.write(f"{cor} **{r['grupo_nome']}** - Status: {r['status']} | Saída: {r['saida']}")

elif aba == "📜 Expirados":
    st.title("📜 Histórico de Expirações")
    df_exp = pd.read_sql_query("SELECT grupo_nome, nome, username, entrada, saida FROM membros WHERE status = 'Expirado'", conn)
    if not df_exp.empty: st.dataframe(df_exp, use_container_width=True, hide_index=True)
    else: st.info("Nenhum registro de expiração.")
