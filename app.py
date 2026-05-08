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

def get_now_br():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

def formatar_data_br(valor):
    if not valor or valor in ["Vitalício", "Aguardando", "Aguardando Entrada", "Não Iniciado"]:
        return valor
    try:
        if "-" in valor and ":" in valor:
            dt = pd.to_datetime(valor)
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
    
    colunas = [("username", "TEXT"), ("telefone", "TEXT"), ("invite_link", "TEXT")]
    for col, tipo in colunas:
        try: cursor.execute(f"ALTER TABLE membros ADD COLUMN {col} {tipo}")
        except: pass
    conn.commit()
    return conn

conn = conectar()

# --- MOTOR DE MONITORAMENTO ---
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
                            # CONVERSÃO EXPLÍCITA PARA INT PARA O BANIMENTO FUNCIONAR
                            bot.ban_chat_member(int(str(g_id).strip()), int(str(u_id).strip()))
                            bot.unban_chat_member(int(str(g_id).strip()), int(str(u_id).strip()))
                        except Exception as e:
                            print(f"Erro ao banir {u_id}: {e}")
                        
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
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=['chat_member'], skip_pending=True), daemon=True).start()
    st.bot_rodando = True

# --- INTERFACE ---
st.set_page_config(page_title="Vanthagem PRO", layout="wide")

def sincronizar_dados():
    try:
        cursor_sync = conn.cursor()
        # Sincronizar nomes dos grupos
        cursor_sync.execute("SELECT DISTINCT grupo_id FROM membros")
        for g in cursor_sync.fetchall():
            try:
                chat = bot.get_chat(int(str(g[0]).strip()))
                cursor_sync.execute("UPDATE membros SET grupo_nome = ? WHERE grupo_id = ?", (chat.title, g[0]))
            except: pass
        
        # Sincronizar nomes dos usuários
        cursor_sync.execute("SELECT DISTINCT user_id FROM membros WHERE status != 'Expirado'")
        for u in cursor_sync.fetchall():
            try:
                user_info = bot.get_chat(int(str(u[0]).strip()))
                u_nome = f"{user_info.first_name} {user_info.last_name or ''}".strip()
                u_username = f"@{user_info.username}" if user_info.username else "Sem Username"
                cursor_sync.execute("UPDATE membros SET nome = ?, username = ? WHERE user_id = ?", (u_nome, u_username, u[0]))
            except: pass
        conn.commit()
        return True
    except: return False

st.sidebar.title("💎 Vanthagem PRO")
if st.sidebar.button("🔄 Sincronizar Tudo"):
    if sincronizar_dados(): st.sidebar.success("Sincronizado!")

aba = st.sidebar.radio("Navegação", ["📊 Dashboard Geral", "➕ Novo Cliente", "⚙️ Gerenciar Tempo", "📜 Expirados", "👤 Perfil do Cliente"])

if aba == "📊 Dashboard Geral":
    st.title("📊 Gestão de Membros Ativos")
    df = pd.read_sql_query("SELECT id, grupo_id, grupo_nome, nome, username, status, entrada, saida, invite_link FROM membros WHERE status IN ('Ativo', 'Pendente')", conn)
    
    if not df.empty:
        df['entrada'] = df['entrada'].apply(formatar_data_br)
        df['saida'] = df['saida'].apply(formatar_data_br)
        
        df_grupos = df[['grupo_id', 'grupo_nome']].drop_duplicates()
        dict_grupos = dict(zip(df_grupos['grupo_id'], df_grupos['grupo_nome']))
        f_grupo = st.sidebar.selectbox("Filtrar por Grupo", options=["Todos"] + list(dict_grupos.keys()), format_func=lambda x: "Todos" if x == "Todos" else dict_grupos[x])
        
        dff = df.copy()
        if f_grupo != "Todos": dff = dff[dff['grupo_id'] == f_grupo]

        st.dataframe(dff[['grupo_nome', 'nome', 'username', 'status', 'entrada', 'saida']], use_container_width=True)
        
        st.subheader("🔗 Links de Convite Pendentes")
        pendentes = dff[dff['status'] == 'Pendente']
        for _, p in pendentes.iterrows():
            with st.expander(f"Link: {p['nome']} - {p['grupo_nome']}"):
                st.code(p['invite_link'])
    else: st.info("Nenhum membro ativo.")

elif aba == "➕ Novo Cliente":
    st.title("➕ Gerar Acesso")
    
    colA, colB = st.columns(2)
    g_id_in = colA.text_input("ID do Grupo (Ex: -100...)")
    u_id_in = colB.text_input("ID do Usuário (Ex: 123456)")

    if st.button("🔍 VALIDAR E BUSCAR DADOS"):
        try:
            # LIMPEZA DE ESPAÇOS E CONVERSÃO
            gid = int(g_id_in.strip())
            uid = int(u_id_in.strip())
            
            chat_info = bot.get_chat(gid)
            user_info = bot.get_chat(uid)
            
            st.session_state.g_nome = chat_info.title
            st.session_state.u_nome = f"{user_info.first_name} {user_info.last_name or ''}".strip()
            st.session_state.u_user = f"@{user_info.username}" if user_info.username else "Sem Username"
            st.success(f"✅ Grupo: {st.session_state.g_nome} | Usuário: {st.session_state.u_nome}")
        except Exception as e:
            st.error(f"Erro na validação: {e}. Verifique se o Bot está no grupo e se o ID está correto.")

    if 'g_nome' in st.session_state:
        with st.form("confirmar_cadastro"):
            f_nome = st.text_input("Nome do Cliente", value=st.session_state.u_nome)
            f_user = st.text_input("Username", value=st.session_state.u_user)
            f_tel = st.text_input("Telefone (Opcional)")
            tempo = st.selectbox("Duração", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
            
            if st.form_submit_button("GERAR LINK E SALVAR"):
                try:
                    link_obj = bot.create_chat_invite_link(int(g_id_in.strip()), member_limit=1)
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, username, entrada, saida, duracao_txt, status, invite_link, telefone) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                   (g_id_in.strip(), st.session_state.g_nome, u_id_in.strip(), f_nome, f_user, "Aguardando", "Aguardando", tempo, "Pendente", link_obj.invite_link, f_tel))
                    conn.commit()
                    st.success("✅ Cliente cadastrado!")
                    st.code(link_obj.invite_link)
                except Exception as e:
                    st.error(f"Erro ao gerar link: {e}")

# ... (Manter as outras abas seguindo a lógica de converter IDs para int)
