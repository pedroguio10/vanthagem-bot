import os; os.system('python reparar_banco.py')
import streamlit as st
import telebot
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import threading
import time

# --- CONFIGURAÇÕES DO BOT ---
TOKEN = '8506261472:AAEFl-coVYJtnVjlILf04n5WJlaMNgqDv84'
bot = telebot.TeleBot(TOKEN)

# Função que cria o banco de dados AUTOMATICAMENTE
def conectar():
    conn = sqlite3.connect('vanthagem_v2.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS membros 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    grupo_id TEXT, grupo_nome TEXT, 
                    user_id TEXT, nome TEXT, 
                    entrada TEXT, saida TEXT, 
                    duracao_txt TEXT, status TEXT)''')
    conn.commit()
    return conn

conn = conectar()

# --- MOTOR DE MONITORAMENTO (Roda sozinho no servidor) ---
def monitor_geral():
    while True:
        try:
            conn_thread = sqlite3.connect('vanthagem_v2.db')
            cursor = conn_thread.cursor()
            agora = datetime.now()
            
            # Remove quem já venceu o tempo
            cursor.execute("SELECT id, grupo_id, user_id, nome, saida FROM membros WHERE status = 'Ativo'")
            ativos = cursor.fetchall()
            for m in ativos:
                m_id, g_id, u_id, nome, data_saida = m
                if data_saida == "Vitalício": continue
                limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M")
                if agora >= limite:
                    try:
                        bot.ban_chat_member(g_id, u_id)
                        bot.unban_chat_member(g_id, u_id)
                        cursor.execute("DELETE FROM membros WHERE id = ?", (m_id,))
                        conn_thread.commit()
                    except:
                        pass
            conn_thread.close()
        except:
            pass
        time.sleep(30)

# Ativa o sensor de entrada: quando o cliente entrar pelo link, o tempo começa!
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
            agora = datetime.now()
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

if 'bot_thread' not in st.session_state:
    threading.Thread(target=monitor_geral, daemon=True).start()
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=['chat_member']), daemon=True).start()
    st.session_state['bot_thread'] = True

# --- INTERFACE DO SEU SITE ---
st.set_page_config(page_title="Vanthagem Assinaturas", layout="wide")

st.sidebar.title("💎 Vanthagem Assinaturas")
aba = st.sidebar.selectbox("Ir para:", ["Dashboard Geral", "Cadastrar Cliente"])

if aba == "Dashboard Geral":
    st.title("📊 Gestão de Membros")
    try:
        df = pd.read_sql_query("SELECT grupo_nome, nome, status, entrada, saida FROM membros", conn)
        if not df.empty:
            df.columns = ['Grupo', 'Cliente', 'Status', 'Início', 'Fim/Expiração']
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nenhum cliente no sistema. Vá em 'Cadastrar Cliente' para começar.")
    except:
        st.warning("O sistema está preparando o banco de dados. Adicione o primeiro cliente para ativar.")

elif aba == "Cadastrar Cliente":
    st.title("➕ Gerar Acesso Inteligente")
    with st.form("cadastro"):
        col1, col2 = st.columns(2)
        with col1:
            g_id = st.text_input("ID do Grupo (-100...)")
            u_id = st.text_input("ID do Usuário (Cliente)")
        with col2:
            g_nome = st.text_input("Nome do Grupo")
            u_nome = st.text_input("Nome do Cliente")
        tempo = st.selectbox("Tempo", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        btn = st.form_submit_button("GERAR LINK E ADICIONAR AO SISTEMA")
        
        if btn:
            try:
                # O Bot cria o link de uso único aqui
                link_obj = bot.create_chat_invite_link(g_id, member_limit=1)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida, duracao_txt, status) VALUES (?,?,?,?,?,?,?,?)",
                               (g_id, g_nome, u_id, u_nome, "Aguardando Entrada", "Aguardando Entrada", tempo, "Pendente"))
                conn.commit()
                st.success("✅ Tudo pronto! Agora é só mandar o link abaixo para o cliente.")
                st.code(f"{link_obj.invite_link}")
                st.info("O tempo só começará a contar quando o ID do cliente entrar no grupo.")
            except Exception as e:
                st.error(f"Erro: Verifique se o Bot é admin do grupo. Detalhe: {e}")
