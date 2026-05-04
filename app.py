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

# --- BANCO DE DADOS ---
def conectar():
    conn = sqlite3.connect('vanthagem_pro.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS membros 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    grupo_id TEXT, grupo_nome TEXT, 
                    user_id TEXT, nome TEXT, 
                    entrada TEXT, saida TEXT)''')
    conn.commit()
    return conn

conn = conectar()

# --- MOTOR DE REMOÇÃO AUTOMÁTICA (RODA 24H) ---
def monitor_expiracao():
    while True:
        try:
            conn_thread = sqlite3.connect('vanthagem_pro.db')
            cursor = conn_thread.cursor()
            agora = datetime.now()
            
            cursor.execute("SELECT id, grupo_id, user_id, nome, saida FROM membros")
            membros = cursor.fetchall()
            
            for m in membros:
                m_id, g_id, u_id, nome, data_saida = m
                if data_saida == "Vitalício":
                    continue
                
                limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M")
                if agora >= limite:
                    # Remove do Telegram
                    bot.ban_chat_member(g_id, u_id)
                    bot.unban_chat_member(g_id, u_id)
                    # Remove do Banco
                    cursor.execute("DELETE FROM membros WHERE id = ?", (m_id,))
                    conn_thread.commit()
            conn_thread.close()
        except Exception as e:
            print(f"Erro no monitor: {e}")
        time.sleep(60)

# Inicia o monitor em segundo plano apenas uma vez
if 'monitor_running' not in st.session_state:
    threading.Thread(target=monitor_expiracao, daemon=True).start()
    st.session_state['monitor_running'] = True

# --- INTERFACE VISUAL ---
st.set_page_config(page_title="Vanthagem Assinaturas", layout="wide")

# Estilo para esconder menus padrões do Streamlit e deixar mais clean
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stButton>button {width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white;}
    </style>
    """, unsafe_allow_html=True)

st.sidebar.title("💎 Vanthagem Assinaturas")
aba = st.sidebar.selectbox("Ir para:", ["Dashboard Geral", "Adicionar Novo Membro"])

if aba == "Dashboard Geral":
    st.title("📊 Gestão de Grupos e Membros")
    
    df = pd.read_sql_query("SELECT * FROM membros", conn)
    
    if not df.empty:
        # Calcular tempo restante em horas para a lógica das cores
        def calc_horas(row):
            if row['saida'] == "Vitalício": return 9999
            saida = datetime.strptime(row['saida'], "%d/%m/%Y %H:%M")
            restante = saida - datetime.now()
            return restante.total_seconds() / 3600

        df['horas_restantes'] = df.apply(calc_horas, axis=1)

        # A lógica do fundo vermelho (Menos de 24h)
        def highlight_expiring(row):
            if row.horas_restantes <= 24:
                return ['background-color: #ff4d4d; color: white; font-weight: bold'] * len(row)
            return [''] * len(row)

        # Preparar tabela limpa
        display_df = df[['grupo_nome', 'nome', 'entrada', 'saida']].copy()
        display_df.columns = ['Grupo', 'Membro', 'Data de Entrada', 'Expira em']
        
        st.dataframe(display_df.style.apply(highlight_expiring, axis=1), use_container_width=True)
    else:
        st.info("Nenhum membro ativo nos seus grupos.")

elif aba == "Adicionar Novo Membro":
    st.title("➕ Cadastrar Novo Cliente")
    
    with st.expander("Como pegar as informações?", expanded=False):
        st.write("1. Adicione o bot no seu grupo como Admin.")
        st.write("2. Para o ID do Grupo: Use o bot @RawDataBot no grupo.")
        st.write("3. Para o ID do Usuário: Use o bot @userinfobot com o cliente.")

    with st.form("cadastro"):
        col1, col2 = st.columns(2)
        with col1:
            g_id = st.text_input("ID do Grupo (ex: -100...)")
            g_nome = st.text_input("Nome do Grupo (ex: VIP Estratégias)")
        with col2:
            u_id = st.text_input("ID do Usuário (ID numérico do Telegram)")
            u_nome = st.text_input("Nome do Cliente")
        
        tempo = st.selectbox("Tempo de Permanência", 
                            ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        
        btn = st.form_submit_button("ADICIONAR AO SISTEMA")
        
        if btn:
            agora = datetime.now()
            # Lógica de tempo
            deltas = {
                "30 minutos": timedelta(minutes=30), "1 hora": timedelta(hours=1),
                "1 semana": timedelta(weeks=1), "15 dias": timedelta(days=15),
                "30 dias": timedelta(days=30), "60 dias": timedelta(days=60),
                "90 dias": timedelta(days=90), "1 ano": timedelta(days=365),
                "2 anos": timedelta(days=730)
            }
            
            data_entrada = agora.strftime("%d/%m/%Y %H:%M")
            data_saida = (agora + deltas[tempo]).strftime("%d/%m/%Y %H:%M") if tempo != "Vitalício" else "Vitalício"
            
            cursor = conn.cursor()
            cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida) VALUES (?,?,?,?,?,?)",
                           (g_id, g_nome, u_id, u_nome, data_entrada, data_saida))
            conn.commit()
            st.success(f"✅ {u_nome} adicionado com sucesso ao grupo {g_nome}!")
