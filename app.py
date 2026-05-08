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

# --- FUNÇÃO DE HORÁRIO BRASÍLIA (FIXO UTC-3) ---
def get_now_br():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3)))

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
    conn.commit()
    return conn

conn = conectar()

# --- SINCRONIZAÇÃO POR ID (BUSCA DADOS REAIS NO TELEGRAM) ---
def sincronizar_pelo_id():
    try:
        cursor_sync = conn.cursor()
        cursor_sync.execute("SELECT DISTINCT user_id, grupo_id FROM membros")
        pares = cursor_sync.fetchall()
        
        for u_id, g_id in pares:
            try:
                # Atualiza dados do Usuário
                user = bot.get_chat(int(u_id))
                novo_nome = f"{user.first_name} {user.last_name or ''}".strip()
                novo_user = f"@{user.username}" if user.username else "Sem Username"
                
                # Atualiza dados do Grupo
                grupo = bot.get_chat(int(g_id))
                novo_grupo_nome = grupo.title
                
                cursor_sync.execute("""
                    UPDATE membros 
                    SET nome = ?, username = ?, grupo_nome = ? 
                    WHERE user_id = ? AND grupo_id = ?
                """, (novo_nome, novo_user, novo_grupo_nome, u_id, g_id))
            except Exception as e:
                print(f"Erro ao sincronizar ID {u_id}: {e}")
                continue
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro na sincronização: {e}")
        return False

# --- MOTOR DE MONITORAMENTO ---
def monitor_geral():
    while True:
        try:
            conn_thread = sqlite3.connect('vanthagem_v2.db')
            cursor = conn_thread.cursor()
            agora = get_now_br()
            
            cursor.execute("SELECT id, grupo_id, user_id, saida FROM membros WHERE status = 'Ativo'")
            ativos = cursor.fetchall()
            for m in ativos:
                m_id, g_id, u_id, data_saida = m
                if data_saida == "Vitalício": continue
                
                try:
                    limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M").replace(tzinfo=timezone(timedelta(hours=-3)))
                    if agora >= limite:
                        try:
                            bot.ban_chat_member(int(g_id), int(u_id))
                            bot.unban_chat_member(int(g_id), int(u_id))
                        except: pass
                        cursor.execute("UPDATE membros SET status = 'Expirado' WHERE id = ?", (m_id,))
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
        cursor.execute("SELECT id, duracao_txt FROM membros WHERE user_id = ? AND grupo_id = ? AND status = 'Pendente'", (u_id, g_id))
        res = cursor.fetchone()
        if res:
            m_id, duracao = res
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
            conn_in.commit()
        conn_in.close()

if not hasattr(st, "bot_rodando"):
    bot.remove_webhook()
    threading.Thread(target=monitor_geral, daemon=True).start()
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=['chat_member'], skip_pending=True), daemon=True).start()
    st.bot_rodando = True

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Vanthagem PRO", layout="wide")

# Sidebar com botão de sincronizar
st.sidebar.title("💎 Vanthagem PRO")
if st.sidebar.button("🔄 Sincronizar Tudo (IDs)"):
    if sincronizar_pelo_id():
        st.sidebar.success("Dados atualizados!")
        st.rerun()

aba = st.sidebar.radio("Navegação", ["📊 Dashboard Geral", "➕ Novo Cliente", "⚙️ Gerenciar Tempo", "📜 Expirados"])

# --- DASHBOARD ---
if aba == "📊 Dashboard Geral":
    st.title("📊 Gestão de Membros")
    df = pd.read_sql_query("SELECT grupo_nome, nome, username, status, entrada, saida FROM membros WHERE status IN ('Ativo', 'Pendente')", conn)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else: st.info("Nenhum membro ativo ou pendente.")

# --- NOVO CLIENTE ---
elif aba == "➕ Novo Cliente":
    st.title("➕ Cadastrar Novo Acesso")
    with st.form("cadastro"):
        col1, col2 = st.columns(2)
        g_id = col1.text_input("ID do Grupo (-100...)")
        u_id = col1.text_input("ID do Usuário")
        g_nome = col2.text_input("Nome do Grupo")
        u_nome = col2.text_input("Nome do Cliente")
        tempo = st.selectbox("Duração", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        if st.form_submit_button("GERAR LINK E SALVAR"):
            try:
                link = bot.create_chat_invite_link(int(g_id), member_limit=1).invite_link
                cursor = conn.cursor()
                cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida, duracao_txt, status, invite_link) VALUES (?,?,?,?,?,?,?,?,?)",
                               (g_id, g_nome, u_id, u_nome, "Aguardando", "Aguardando", tempo, "Pendente", link))
                conn.commit()
                st.success("✅ Link Gerado!"); st.code(link)
            except Exception as e: st.error(f"Erro: {e}")

# --- GERENCIAR TEMPO (COM CALENDÁRIO RESTAURADO) ---
elif aba == "⚙️ Gerenciar Tempo":
    st.title("⚙️ Personalizar Expiração")
    df_edit = pd.read_sql_query("SELECT id, nome, grupo_nome, saida FROM membros WHERE status = 'Ativo'", conn)
    
    if not df_edit.empty:
        escolha = st.selectbox("Selecione o Cliente:", df_edit['nome'] + " (" + df_edit['grupo_nome'] + ")")
        m_id = int(df_edit[df_edit['nome'] + " (" + df_edit['grupo_nome'] + ")" == escolha]['id'].values[0])
        
        # Calendário Personalizado
        st.subheader("Alterar Data de Saída")
        col_d, col_h = st.columns(2)
        nova_data = col_d.date_input("Selecione a Data")
        nova_hora = col_h.time_input("Selecione a Hora")
        
        if st.button("ATUALIZAR DATA PERSONALIZADA"):
            data_final = datetime.combine(nova_data, nova_hora).strftime("%d/%m/%Y %H:%M")
            cursor = conn.cursor()
            cursor.execute("UPDATE membros SET saida = ? WHERE id = ?", (data_final, m_id))
            conn.commit()
            st.success(f"✅ Nova expiração definida para: {data_final}")
            st.rerun()
    else:
        st.info("Nenhum cliente ativo para gerenciar.")

# --- EXPIRADOS (COM EXCLUSÃO DE HISTÓRICO) ---
elif aba == "📜 Expirados":
    st.title("📜 Histórico de Membros Expirados")
    
    if st.button("🚨 EXCLUIR TODO O HISTÓRICO DE EXPIRADOS"):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM membros WHERE status = 'Expirado'")
        conn.commit()
        st.warning("Todo o histórico de expirados foi removido.")
        st.rerun()

    df_exp = pd.read_sql_query("SELECT grupo_nome, nome, username, entrada, saida FROM membros WHERE status = 'Expirado'", conn)
    if not df_exp.empty:
        st.dataframe(df_exp, use_container_width=True)
    else:
        st.info("Nenhum registro de expiração encontrado.")
