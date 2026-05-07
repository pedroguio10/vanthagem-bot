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
    conn = sqlite3.connect('vanthagem_v2.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Tabela principal de membros
    cursor.execute('''CREATE TABLE IF NOT EXISTS membros 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    grupo_id TEXT, grupo_nome TEXT, 
                    user_id TEXT, nome TEXT, 
                    entrada TEXT, saida TEXT, 
                    duracao_txt TEXT, status TEXT,
                    invite_link TEXT, telefone TEXT)''')
    
    # Nova tabela para o Histórico de Ações (O Dossiê)
    cursor.execute('''CREATE TABLE IF NOT EXISTS historico 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT, nome TEXT, 
                    acao TEXT, grupo_nome TEXT, 
                    data_hora TEXT, detalhes TEXT)''')
    
    # Migrações automáticas
    try: cursor.execute("ALTER TABLE membros ADD COLUMN invite_link TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE membros ADD COLUMN telefone TEXT")
    except: pass
    
    conn.commit()
    return conn

conn = conectar()

# --- MOTOR DE MONITORAMENTO (Roda 24/7) ---
def monitor_geral():
    while True:
        try:
            conn_thread = sqlite3.connect('vanthagem_v2.db')
            cursor = conn_thread.cursor()
            agora = datetime.now()
            
            cursor.execute("SELECT id, grupo_id, user_id, nome, saida, grupo_nome FROM membros WHERE status = 'Ativo'")
            ativos = cursor.fetchall()
            for m in ativos:
                m_id, g_id, u_id, nome, data_saida, g_nome = m
                if data_saida == "Vitalício": continue
                
                try:
                    limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M")
                    if agora >= limite:
                        try:
                            bot.ban_chat_member(g_id, u_id)
                            bot.unban_chat_member(g_id, u_id)
                        except:
                            pass
                        
                        # Atualiza status
                        cursor.execute("UPDATE membros SET status = 'Expirado' WHERE id = ?", (m_id,))
                        
                        # Salva no histórico
                        data_str = agora.strftime("%d/%m/%Y %H:%M")
                        cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                                       (u_id, nome, "Expirou/Saiu", g_nome, data_str, f"Tempo finalizado ({data_saida})"))
                        conn_thread.commit()
                except:
                    continue
            conn_thread.close()
        except:
            pass
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
            
            # Salva no histórico
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
st.set_page_config(page_title="Vanthagem CRM", layout="wide")

st.sidebar.title("💎 Vanthagem PRO")
aba = st.sidebar.radio("Navegação", [
    "📊 Dashboard Geral", 
    "➕ Novo Cliente", 
    "⚙️ Gerenciar Tempo", 
    "📜 Expirados", 
    "👤 Perfil do Cliente"
])

# Helper para conversão
def verificar_urgencia(data_str):
    if data_str in ["Vitalício", "Aguardando Entrada"]: return False
    try:
        data_fim = datetime.strptime(data_str, "%d/%m/%Y %H:%M")
        diff = data_fim - datetime.now()
        return diff.total_seconds() < 86400 and diff.total_seconds() > 0
    except:
        return False

# Sincronizador Automático de Nomes de Grupos (Roda no background visual)
try:
    cursor_sync = conn.cursor()
    cursor_sync.execute("SELECT DISTINCT grupo_id FROM membros")
    for g in cursor_sync.fetchall():
        try:
            chat_info = bot.get_chat(g[0])
            cursor_sync.execute("UPDATE membros SET grupo_nome = ? WHERE grupo_id = ?", (chat_info.title, g[0]))
        except: pass
    conn.commit()
except: pass

if aba == "📊 Dashboard Geral":
    st.title("📊 Gestão de Membros Ativos")
    
    df = pd.read_sql_query("SELECT id, grupo_nome, nome, status, entrada, saida, invite_link FROM membros WHERE status IN ('Ativo', 'Pendente')", conn)
    
    if not df.empty:
        df['critico'] = df['saida'].apply(verificar_urgencia)
        
        st.sidebar.subheader("Filtros")
        f_grupo = st.sidebar.multiselect("Filtrar por Grupo", options=df['grupo_nome'].unique())
        f_status = st.sidebar.multiselect("Status", options=['Ativo', 'Pendente'], default=['Ativo', 'Pendente'])
        f_critico = st.sidebar.checkbox("Mostrar apenas Críticos (<24h)")

        dff = df.copy()
        if f_grupo: dff = dff[dff['grupo_nome'].isin(f_grupo)]
        if f_status: dff = dff[dff['status'].isin(f_status)]
        if f_critico: dff = dff[dff['critico'] == True]

        dff['status_order'] = dff['status'].map({'Pendente': 0, 'Ativo': 1})
        dff = dff.sort_values(by=['status_order', 'id'], ascending=[True, False])

        def highlight_critico(row):
            return ['background-color: #ff4b4b; color: white' if row.critico and row.status == 'Ativo' else '' for _ in row]

        colunas_show = ['grupo_nome', 'nome', 'status', 'entrada', 'saida']
        styled_df = dff.style.apply(highlight_critico, axis=1)
        st.dataframe(styled_df, column_order=colunas_show, width='stretch')

        st.divider()
        st.subheader("🔗 Recuperar Acesso (Pendentes)")
        pendentes = dff[dff['status'] == 'Pendente']['nome'].tolist()
        if pendentes:
            cliente_selecionado = st.selectbox("Selecione um cliente para ver o link:", options=pendentes)
            if cliente_selecionado:
                link = dff[dff['nome'] == cliente_selecionado]['invite_link'].values[0]
                st.code(link)
        else:
            st.info("Nenhum convite pendente no momento.")
    else:
        st.info("Nenhum dado encontrado.")

elif aba == "➕ Novo Cliente":
    st.title("➕ Cadastrar Novo Acesso")
    
    # Inicializa variáveis de sessão para o Smart Sync do Grupo
    if 'grupo_verificado' not in st.session_state:
        st.session_state['grupo_verificado'] = ""
    
    with st.container(border=True):
        st.subheader("1. Identificação do Grupo")
        colA, colB = st.columns([2, 1])
        with colA:
            g_id_input = st.text_input("ID do Grupo (Ex: -100...)")
        with colB:
            st.markdown("<br>", unsafe_allow_html=True) # Espaçamento
            if st.button("🔍 Validar ID", use_container_width=True):
                try:
                    chat_info = bot.get_chat(g_id_input)
                    st.session_state['grupo_verificado'] = chat_info.title
                    st.success(f"✅ Encontrado: {chat_info.title}")
                except:
                    st.error("Grupo não encontrado. O bot é Admin?")
        
        g_nome_final = st.text_input("Nome do Grupo", value=st.session_state['grupo_verificado'], disabled=True)

    with st.form("cadastro"):
        st.subheader("2. Dados do Cliente")
        col1, col2 = st.columns(2)
        with col1:
            u_id = st.text_input("ID do Usuário (Telegram ID)")
            telefone = st.text_input("Telefone (Opcional)")
        with col2:
            u_nome = st.text_input("Nome do Cliente")
            tempo = st.selectbox("Duração do Plano", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        
        btn = st.form_submit_button("GERAR ACESSO")
        
        if btn:
            if not g_nome_final:
                st.warning("Por favor, valide o ID do Grupo primeiro.")
            else:
                try:
                    link_obj = bot.create_chat_invite_link(g_id_input, member_limit=1)
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida, duracao_txt, status, invite_link, telefone) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                   (g_id_input, g_nome_final, u_id, u_nome, "Aguardando Entrada", "Aguardando Entrada", tempo, "Pendente", link_obj.invite_link, telefone))
                    
                    data_str = datetime.now().strftime("%d/%m/%Y %H:%M")
                    cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                                   (u_id, u_nome, "Link Gerado", g_nome_final, data_str, "Aguardando uso do link"))
                    conn.commit()
                    
                    st.success("✅ Cliente pré-cadastrado!")
                    st.code(link_obj.invite_link)
                except Exception as e:
                    st.error(f"Erro ao gerar link. Erro: {e}")

elif aba == "⚙️ Gerenciar Tempo":
    st.title("⚙️ Renovação e Gestão de Tempo")
    df_edit = pd.read_sql_query("SELECT id, user_id, nome, grupo_nome, saida, status FROM membros WHERE status != 'Pendente'", conn)
    
    if not df_edit.empty:
        escolha = st.selectbox("Selecione o Cliente:", df_edit['nome'] + " (" + df_edit['grupo_nome'] + ")")
        linha = df_edit[df_edit['nome'] + " (" + df_edit['grupo_nome'] + ")" == escolha].iloc[0]
        m_id, u_id, c_nome, g_nome, data_atual_saida = linha['id'], linha['user_id'], linha['nome'], linha['grupo_nome'], linha['saida']
        
        st.write(f"Expiração Atual: **{data_atual_saida}**")
        opcao_tempo = st.radio("Quanto tempo adicionar?", ["30 min", "1 hora", "1 dia", "15 dias", "30 dias", "60 dias", "Data Personalizada"])
        
        nova_data = None
        if opcao_tempo == "Data Personalizada":
            col1, col2 = st.columns(2)
            with col1: nova_data_calendario = st.date_input("Escolha a nova data")
            with col2: nova_hora = st.time_input("Escolha a nova hora")
            nova_data = datetime.combine(nova_data_calendario, nova_hora).strftime("%d/%m/%Y %H:%M")
        
        if st.button("CONFIRMAR RENOVAÇÃO"):
            formato = "%d/%m/%Y %H:%M"
            base = datetime.now() if data_atual_saida == "Expirado" else datetime.strptime(data_atual_saida, formato)
            
            if not nova_data:
                acrescimo = {"30 min": timedelta(minutes=30), "1 hora": timedelta(hours=1), "1 dia": timedelta(days=1), "15 dias": timedelta(days=15), "30 dias": timedelta(days=30), "60 dias": timedelta(days=60)}
                nova_data = (base + acrescimo[opcao_tempo]).strftime(formato)
            
            cursor = conn.cursor()
            cursor.execute("UPDATE membros SET saida = ?, status = 'Ativo' WHERE id = ?", (nova_data, int(m_id)))
            data_str = datetime.now().strftime("%d/%m/%Y %H:%M")
            cursor.execute("INSERT INTO historico (user_id, nome, acao, grupo_nome, data_hora, detalhes) VALUES (?,?,?,?,?,?)",
                           (u_id, c_nome, "Renovação", g_nome, data_str, f"Prorrogado para {nova_data}"))
            conn.commit()
            st.success(f"✅ Tempo atualizado! Nova expiração: {nova_data}")
            st.balloons()
    else:
        st.info("Não há clientes ativos ou expirados para gerenciar.")

elif aba == "📜 Expirados":
    st.title("📜 Histórico de Clientes Expirados")
    df_exp = pd.read_sql_query("SELECT grupo_nome, nome, entrada, saida FROM membros WHERE status = 'Expirado'", conn)
    if not df_exp.empty:
        st.dataframe(df_exp, width='stretch')
    else:
        st.info("Nenhum cliente expirado no sistema.")

elif aba == "👤 Perfil do Cliente":
    st.title("👤 Dossiê do Cliente")
    df_users = pd.read_sql_query("SELECT DISTINCT user_id, nome FROM membros", conn)
    
    if not df_users.empty:
        cliente_busca = st.selectbox("Selecione um cliente para investigar:", options=df_users['nome'].tolist())
        user_id_busca = df_users[df_users['nome'] == cliente_busca]['user_id'].values[0]
        
        # Puxa informações gerais do membro
        df_dados = pd.read_sql_query("SELECT telefone, status, grupo_nome, saida FROM membros WHERE user_id = ?", conn, params=(user_id_busca,))
        telefone = df_dados['telefone'].dropna().unique()
        telefone_txt = telefone[0] if len(telefone) > 0 and telefone[0] != "" else "Não informado"
        
        with st.container(border=True):
            st.subheader(f"📋 Ficha de {cliente_busca}")
            col1, col2 = st.columns(2)
            col1.write(f"**Telegram ID:** {user_id_busca}")
            col2.write(f"**Telefone:** {telefone_txt}")
            
            st.write("**Situação nos Grupos:**")
            for index, row in df_dados.iterrows():
                cor = "🟢" if row['status'] == 'Ativo' else ("🟡" if row['status'] == 'Pendente' else "🔴")
                st.write(f"{cor} {row['grupo_nome']} - Status: {row['status']} (Expira/Expirou em: {row['saida']})")

        st.subheader("⏱️ Linha do Tempo de Atividades")
        df_hist = pd.read_sql_query("SELECT data_hora, acao, grupo_nome, detalhes FROM historico WHERE user_id = ? ORDER BY id DESC", conn, params=(user_id_busca,))
        if not df_hist.empty:
            st.dataframe(df_hist, width='stretch')
        else:
            st.info("Nenhum histórico registrado para este cliente ainda (os registros começaram agora).")
    else:
        st.info("Não há clientes cadastrados.")
