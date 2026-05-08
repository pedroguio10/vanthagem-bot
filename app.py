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
    # Define o fuso horário de Brasília (UTC-3)
    return datetime.now(timezone(timedelta(hours=-3)))

def conectar():
    conn = sqlite3.connect('vanthagem_v2.db', check_same_thread=False)
    cursor = conn.cursor()
    # Estrutura baseada no seu backup [cite: 2, 3]
    cursor.execute('''CREATE TABLE IF NOT EXISTS membros 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    grupo_id TEXT, grupo_nome TEXT, 
                    user_id TEXT, nome TEXT, username TEXT,
                    entrada TEXT, saida TEXT, 
                    duracao_txt TEXT, status TEXT,
                    invite_link TEXT, telefone TEXT)''')
    
    # Tabela de histórico para auditoria
    cursor.execute('''CREATE TABLE IF NOT EXISTS historico 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT, nome TEXT, acao TEXT, 
                    grupo_nome TEXT, data_hora TEXT, detalhes TEXT)''')
    
    # Migração para garantir colunas novas se necessário
    try: cursor.execute("ALTER TABLE membros ADD COLUMN username TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE membros ADD COLUMN telefone TEXT")
    except: pass
    
    conn.commit()
    return conn

conn = conectar()

# --- SINCRONIZAÇÃO POR ID ---
def sincronizar_dados():
    try:
        cursor_sync = conn.cursor()
        # Atualiza nomes dos grupos pelo ID
        cursor_sync.execute("SELECT DISTINCT grupo_id FROM membros")
        for (g_id,) in cursor_sync.fetchall():
            try:
                chat = bot.get_chat(int(g_id))
                cursor_sync.execute("UPDATE membros SET grupo_nome = ? WHERE grupo_id = ?", (chat.title, g_id))
            except: pass
        
        # Atualiza Nome e Username do usuário pelo ID
        cursor_sync.execute("SELECT DISTINCT user_id FROM membros")
        for (u_id,) in cursor_sync.fetchall():
            try:
                u_info = bot.get_chat(int(u_id))
                novo_nome = f"{u_info.first_name} {u_info.last_name or ''}".strip()
                novo_user = f"@{u_info.username}" if u_info.username else "Sem Username"
                cursor_sync.execute("UPDATE membros SET nome = ?, username = ? WHERE user_id = ?", (novo_nome, novo_user, u_id))
            except: pass
        conn.commit()
        return True
    except: return False

# --- MOTOR DE MONITORAMENTO (BRASÍLIA) ---
def monitor_geral():
    while True:
        try:
            conn_thread = sqlite3.connect('vanthagem_v2.db')
            cursor = conn_thread.cursor()
            agora = get_now_br() # Uso do fuso horário correto [cite: 4]
            
            cursor.execute("SELECT id, grupo_id, user_id, nome, saida, grupo_nome FROM membros WHERE status = 'Ativo'")
            ativos = cursor.fetchall()
            for m in ativos:
                m_id, g_id, u_id, nome, data_saida, g_nome = m
                if data_saida == "Vitalício": continue
                
                try:
                    limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M").replace(tzinfo=timezone(timedelta(hours=-3)))
                    if agora >= limite: [cite: 6]
                        try:
                            bot.ban_chat_member(int(g_id), int(u_id)) [cite: 7]
                            bot.unban_chat_member(int(g_id), int(u_id))
                        except: pass
                        
                        cursor.execute("UPDATE membros SET status = 'Expirado' WHERE id = ?", (m_id,))
                        cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                                       (u_id, nome, "Expirou", g_nome, agora.strftime("%d/%m/%Y %H:%M"), "Removido automaticamente"))
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
        cursor.execute("SELECT id, duracao_txt, nome, grupo_nome FROM membros WHERE user_id = ? AND grupo_id = ? AND status = 'Pendente'", (u_id, g_id)) [cite: 10, 11]
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
            data_saida = (agora + deltas[duracao]).strftime("%d/%m/%Y %H:%M") if duracao != "Vitalício" else "Vitalício" [cite: 13]
            
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

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Vanthagem PRO", layout="wide") [cite: 14]

# Botão de Sincronização na Sidebar
if st.sidebar.button("🔄 Sincronizar Tudo"):
    if sincronizar_dados(): st.sidebar.success("Dados Atualizados via ID!")
    else: st.sidebar.error("Erro na sincronização.")

aba = st.sidebar.radio("Navegação", ["📊 Dashboard Geral", "➕ Novo Cliente", "⚙️ Gerenciar Tempo", "📜 Expirados"])

if aba == "📊 Dashboard Geral":
    st.title("📊 Gestão de Membros") [cite: 15]
    df = pd.read_sql_query("SELECT grupo_nome, nome, username, status, entrada, saida FROM membros WHERE status IN ('Ativo', 'Pendente')", conn)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else: st.info("Nenhum membro ativo.")

elif aba == "➕ Novo Cliente":
    st.title("➕ Cadastrar Novo Acesso")
    with st.form("cadastro"):
        col1, col2 = st.columns(2)
        g_id = col1.text_input("ID do Grupo (-100...)")
        u_id = col1.text_input("ID do Usuário")
        g_nome = col2.text_input("Nome do Grupo")
        u_nome = col2.text_input("Nome do Cliente")
        tempo = st.selectbox("Duração", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        if st.form_submit_button("GERAR ACESSO"):
            try:
                link = bot.create_chat_invite_link(int(g_id), member_limit=1).invite_link [cite: 23]
                cursor = conn.cursor()
                cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida, duracao_txt, status, invite_link) VALUES (?,?,?,?,?,?,?,?,?)",
                               (g_id, g_nome, u_id, u_nome, "Aguardando", "Aguardando", tempo, "Pendente", link))
                conn.commit()
                st.success("✅ Link Gerado!"); st.code(link)
            except Exception as e: st.error(f"Erro: {e}")

elif aba == "⚙️ Gerenciar Tempo":
    st.title("⚙️ Personalizar Expiração")
    df_edit = pd.read_sql_query("SELECT id, nome, grupo_nome, saida FROM membros WHERE status = 'Ativo'", conn)
    if not df_edit.empty:
        escolha = st.selectbox("Selecione o Cliente:", df_edit['nome'] + " (" + df_edit['grupo_nome'] + ")")
        m_id = int(df_edit[df_edit['nome'] + " (" + df_edit['grupo_nome'] + ")" == escolha]['id'].values[0])
        
        # RESTAURADO: Calendário para data personalizada [cite: 27, 28]
        opcao = st.radio("Tipo de Renovação:", ["Tempo Pré-definido", "Data Personalizada"])
        
        if opcao == "Data Personalizada":
            c1, c2 = st.columns(2)
            nova_data_cal = c1.date_input("Nova Data de Expiração")
            nova_hora_cal = c2.time_input("Nova Hora de Expiração")
            data_final = datetime.combine(nova_data_cal, nova_hora_cal).strftime("%d/%m/%Y %H:%M")
        else:
            add_t = st.selectbox("Adicionar:", ["30 min", "1 hora", "1 dia", "15 dias", "30 dias"])
            # Lógica de cálculo baseada no backup [cite: 29, 30]
            base = get_now_br()
            deltas = {"30 min": timedelta(minutes=30), "1 hora": timedelta(hours=1), "1 dia": timedelta(days=1), "15 dias": timedelta(days=15), "30 dias": timedelta(days=30)}
            data_final = (base + deltas[add_t]).strftime("%d/%m/%Y %H:%M")

        if st.button("CONFIRMAR ALTERAÇÃO"):
            cursor = conn.cursor()
            cursor.execute("UPDATE membros SET saida = ? WHERE id = ?", (data_final, m_id)) [cite: 31]
            conn.commit()
            st.success(f"✅ Nova data: {data_final}"); st.balloons()
    else: st.info("Nenhum cliente ativo para gerenciar.")

elif aba == "📜 Expirados":
    st.title("📜 Histórico de Membros Expirados")
    df_exp = pd.read_sql_query("SELECT grupo_nome, nome, username, entrada, saida FROM membros WHERE status = 'Expirado'", conn)
    
    if not df_exp.empty:
        st.dataframe(df_exp, use_container_width=True)
        st.divider()
        # NOVO: Opção de excluir todo o histórico de expirados
        if st.button("🚨 EXCLUIR TODO O HISTÓRICO DE EXPIRADOS"):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM membros WHERE status = 'Expirado'")
            conn.commit()
            st.warning("Todo o histórico de membros expirados foi removido.")
            st.rerun()
    else: st.info("Nenhum registro de expiração.")
