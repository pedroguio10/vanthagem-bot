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

def conectar():
    conn = sqlite3.connect('vanthagem_pro.db', check_same_thread=False)
    cursor = conn.cursor()
    # Adicionamos a coluna 'status' para saber se o cliente já entrou
    cursor.execute('''CREATE TABLE IF NOT EXISTS membros 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    grupo_id TEXT, grupo_nome TEXT, 
                    user_id TEXT, nome TEXT, 
                    entrada TEXT, saida TEXT, 
                    duracao_txt TEXT, status TEXT)''')
    conn.commit()
    return conn

conn = conectar()

# --- MOTOR DE MONITORAMENTO (Entrada e Saída) ---
def monitor_geral():
    while True:
        try:
            conn_thread = sqlite3.connect('vanthagem_pro.db')
            cursor = conn_thread.cursor()
            agora = datetime.now()
            
            # 1. REMOVER QUEM JÁ EXPIROU
            cursor.execute("SELECT id, grupo_id, user_id, nome, saida FROM membros WHERE status = 'Ativo'")
            ativos = cursor.fetchall()
            for m in ativos:
                m_id, g_id, u_id, nome, data_saida = m
                if data_saida == "Vitalício": continue
                limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M")
                if agora >= limite:
                    bot.ban_chat_member(g_id, u_id)
                    bot.unban_chat_member(g_id, u_id)
                    cursor.execute("DELETE FROM membros WHERE id = ?", (m_id,))
                    conn_thread.commit()

            conn_thread.close()
        except Exception as e:
            print(f"Erro no monitor: {e}")
        time.sleep(30)

# 2. DETECTAR ENTRADA NO GRUPO
@bot.chat_member_handler()
def monitorar_entrada(message):
    new_member = message.new_chat_member
    if new_member.status == 'member':
        u_id = str(new_member.user.id)
        g_id = str(message.chat.id)
        
        conn_in = sqlite3.connect('vanthagem_pro.db')
        cursor = conn_in.cursor()
        
        # Procura se esse ID está na lista de "Pendente"
        cursor.execute("SELECT id, duracao_txt FROM membros WHERE user_id = ? AND grupo_id = ? AND status = 'Pendente'", (u_id, g_id))
        res = cursor.fetchone()
        
        if res:
            m_id, duracao = res
            agora = datetime.now()
            # Calcula a saída a partir de AGORA
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

# Inicia bot e monitor
if 'bot_thread' not in st.session_state:
    threading.Thread(target=monitor_geral, daemon=True).start()
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=['chat_member']), daemon=True).start()
    st.session_state['bot_thread'] = True

# --- INTERFACE ---
st.set_page_config(page_title="Vanthagem Assinaturas", layout="wide")

st.sidebar.title("💎 Vanthagem Assinaturas")
aba = st.sidebar.selectbox("Ir para:", ["Dashboard Geral", "Cadastrar Cliente"])

if aba == "Dashboard Geral":
    st.title("📊 Gestão de Membros")
    df = pd.read_sql_query("SELECT grupo_nome, nome, status, entrada,埋saida FROM membros", conn)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum cliente no sistema.")

elif aba == "Cadastrar Cliente":
    st.title("➕ Gerar Acesso")
    with st.form("cadastro"):
        col1, col2 = st.columns(2)
        with col1:
            g_id = st.text_input("ID do Grupo (-100...)")
            u_id = st.text_input("ID do Usuário (Cliente)")
        with col2:
            g_nome = st.text_input("Nome do Grupo")
            u_nome = st.text_input("Nome do Cliente")
        
        tempo = st.selectbox("Tempo", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        btn = st.form_submit_button("GERAR LINK E ADICIONAR")
        
        if btn:
            try:
                # Gera o link único no Telegram
                link_obj = bot.create_chat_invite_link(g_id, member_limit=1)
                link_final = link_obj.invite_link
                
                cursor = conn.cursor()
                cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida, duracao_txt, status) VALUES (?,?,?,?,?,?,?,?)",
                               (g_id, g_nome, u_id, u_nome, "Aguardando", "Aguardando", tempo, "Pendente"))
                conn.commit()
                
                st.success("✅ Cliente pré-cadastrado!")
                st.code(f"Envie este link para o cliente:\n{link_final}", language="text")
                st.warning("O cronômetro só começará a contar quando o cliente entrar no grupo.")
            except Exception as e:
                st.error(f"Erro ao gerar link: {e}. O bot é admin do grupo?")
