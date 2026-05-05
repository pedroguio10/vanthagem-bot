import streamlit as st
import telebot
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import threading
import time

# --- CONFIGURAÇÕES DO BOT ---
# Substitua pelo seu Token se necessário, mas mantive o que estava no backup
TOKEN = '8506261472:AAEFl-coVYJtnVjlILf04n5WJlaMNgqDv84'
bot = telebot.TeleBot(TOKEN)

def conectar():
    conn = sqlite3.connect('vanthagem_v2.db', check_same_thread=False)
    cursor = conn.cursor()
    # Criando ou atualizando a tabela com as novas colunas necessárias
    cursor.execute('''CREATE TABLE IF NOT EXISTS membros 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    grupo_id TEXT, grupo_nome TEXT, 
                    user_id TEXT, nome TEXT, 
                    entrada TEXT, saida TEXT, 
                    duracao_txt TEXT, status TEXT,
                    invite_link TEXT)''')
    
    # Migração automática: Adiciona a coluna invite_link se ela não existir
    try:
        cursor.execute("ALTER TABLE membros ADD COLUMN invite_link TEXT")
    except:
        pass
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
            
            # Filtra apenas quem está Ativo para verificar expiração
            cursor.execute("SELECT id, grupo_id, user_id, nome, saida FROM membros WHERE status = 'Ativo'")
            ativos = cursor.fetchall()
            for m in ativos:
                m_id, g_id, u_id, nome, data_saida = m
                if data_saida == "Vitalício": continue
                
                try:
                    limite = datetime.strptime(data_saida, "%d/%m/%Y %H:%M")
                    if agora >= limite:
                        # Em vez de deletar, apenas remove do grupo e muda status
                        try:
                            bot.ban_chat_member(g_id, u_id)
                            bot.unban_chat_member(g_id, u_id)
                        except:
                            pass
                        cursor.execute("UPDATE membros SET status = 'Expirado' WHERE id = ?", (m_id,))
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

if not hasattr(st, "bot_rodando"):
    bot.remove_webhook()
    threading.Thread(target=monitor_geral, daemon=True).start()
    threading.Thread(target=lambda: bot.infinity_polling(allowed_updates=['chat_member'], skip_pending=True), daemon=True).start()
    st.bot_rodando = True

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Vanthagem Assinaturas", layout="wide")

st.sidebar.title("💎 Vanthagem PRO")
aba = st.sidebar.radio("Navegação", ["📊 Dashboard Geral", "➕ Novo Cliente", "⚙️ Gerenciar Tempo"])

# Helper para converter data e calcular urgência
def verificar_urgencia(data_str):
    if data_str in ["Vitalício", "Aguardando Entrada"]: return False
    try:
        data_fim = datetime.strptime(data_str, "%d/%m/%Y %H:%M")
        diff = data_fim - datetime.now()
        return diff.total_seconds() < 86400 and diff.total_seconds() > 0 # Menos de 24h
    except:
        return False

if aba == "📊 Dashboard Geral":
    st.title("📊 Gestão Inteligente de Membros")
    
    # Busca dados
    query = "SELECT id, grupo_nome, nome, status, entrada, saida, invite_link FROM membros"
    df = pd.read_sql_query(query, conn)
    
    if not df.empty:
        # Adiciona coluna de Urgência para o filtro interno
        df['critico'] = df['saida'].apply(verificar_urgencia)
        
        # --- FILTROS NA BARRA LATERAL ---
        st.sidebar.subheader("Filtros")
        f_grupo = st.sidebar.multiselect("Filtrar por Grupo", options=df['grupo_nome'].unique())
        f_status = st.sidebar.multiselect("Filtrar por Status", options=['Ativo', 'Pendente', 'Expirado'], default=['Ativo', 'Pendente'])
        f_critico = st.sidebar.checkbox("Mostrar apenas Críticos (<24h)")

        # Aplica os filtros no DataFrame
        dff = df.copy()
        if f_grupo: dff = dff[dff['grupo_nome'].isin(f_grupo)]
        if f_status: dff = dff[dff['status'].isin(f_status)]
        if f_critico: dff = dff[dff['critico'] == True]

        # Ordenação: Pendentes no topo, depois por data de saída
        dff['status_order'] = dff['status'].map({'Pendente': 0, 'Ativo': 1, 'Expirado': 2})
        dff = dff.sort_values(by=['status_order', 'id'], ascending=[True, False])

        # Estilização: Linhas vermelhas para críticos
        def highlight_critico(row):
            return ['background-color: #ff4b4b; color: white' if row.critico and row.status == 'Ativo' else '' for _ in row]

        # Exibição da Tabela
        st.write(f"Exibindo {len(dff)} registros")
        colunas_show = ['grupo_nome', 'nome', 'status', 'entrada', 'saida']
        st.dataframe(dff[colunas_show].style.apply(highlight_critico, axis=1), use_container_width=True)

        # --- AÇÕES RÁPIDAS (Visualizar Link) ---
        st.divider()
        st.subheader("🔗 Recuperar Acesso")
        cliente_selecionado = st.selectbox("Selecione um cliente Pendente para ver o link:", 
                                         options=dff[dff['status'] == 'Pendente']['nome'].tolist())
        if cliente_selecionado:
            link = dff[dff['nome'] == cliente_selecionado]['invite_link'].values[0]
            st.info(f"Link de convite para {cliente_selecionado}:")
            st.code(link)

    else:
        st.info("Nenhum dado encontrado.")

elif aba == "➕ Novo Cliente":
    st.title("➕ Cadastrar Novo Acesso")
    with st.form("cadastro"):
        col1, col2 = st.columns(2)
        with col1:
            g_id = st.text_input("ID do Grupo (Ex: -100...)")
            u_id = st.text_input("ID do Usuário (Telegram ID)")
        with col2:
            g_nome = st.text_input("Nome do Grupo")
            u_nome = st.text_input("Nome do Cliente")
        
        tempo = st.selectbox("Duração do Plano", ["30 minutos", "1 hora", "1 semana", "15 dias", "30 dias", "60 dias", "90 dias", "1 ano", "2 anos", "Vitalício"])
        btn = st.form_submit_button("GERAR ACESSO")
        
        if btn:
            try:
                link_obj = bot.create_chat_invite_link(g_id, member_limit=1)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida, duracao_txt, status, invite_link) VALUES (?,?,?,?,?,?,?,?,?)",
                               (g_id, g_nome, u_id, u_nome, "Aguardando Entrada", "Aguardando Entrada", tempo, "Pendente", link_obj.invite_link))
                conn.commit()
                st.success("✅ Cliente pré-cadastrado!")
                st.code(link_obj.invite_link)
            except Exception as e:
                st.error(f"Erro ao gerar link. O bot é admin? Erro: {e}")

elif aba == "⚙️ Gerenciar Tempo":
    st.title("⚙️ Adicionar Tempo de Permanência")
    # Apenas clientes Ativos ou Expirados podem ter tempo adicionado
    df_edit = pd.read_sql_query("SELECT id, nome, grupo_nome, saida, status FROM membros WHERE status != 'Pendente'", conn)
    
    if not df_edit.empty:
        escolha = st.selectbox("Selecione o Cliente:", df_edit['nome'] + " (" + df_edit['grupo_nome'] + ")")
        m_id = int(df_edit[df_edit['nome'] + " (" + df_edit['grupo_nome'] + ")" == escolha]['id'].values[0])
        data_atual_saida = df_edit[df_edit['id'] == m_id]['saida'].values[0]
        
        st.write(f"Expiração Atual: **{data_atual_saida}**")
        
        opcao_tempo = st.radio("Quanto tempo adicionar?", ["30 min", "1 hora", "1 dia", "15 dias", "30 dias", "60 dias", "Data Personalizada"])
        
        nova_data = None
        if opcao_tempo == "Data Personalizada":
            nova_data_calendario = st.date_input("Escolha a nova data")
            nova_hora = st.time_input("Escolha a nova hora")
            nova_data = datetime.combine(nova_data_calendario, nova_hora).strftime("%d/%m/%Y %H:%M")
        
        if st.button("CONFIRMAR ADIÇÃO DE TEMPO"):
            # Lógica para calcular a nova data
            formato = "%d/%m/%Y %H:%M"
            base = datetime.now() if data_atual_saida == "Expirado" else datetime.strptime(data_atual_saida, formato)
            
            if not nova_data:
                acrescimo = {
                    "30 min": timedelta(minutes=30), "1 hora": timedelta(hours=1),
                    "1 dia": timedelta(days=1), "15 dias": timedelta(days=15),
                    "30 dias": timedelta(days=30), "60 dias": timedelta(days=60)
                }
                nova_data = (base + acrescimo[opcao_tempo]).strftime(formato)
            
            cursor = conn.cursor()
            cursor.execute("UPDATE membros SET saida = ?, status = 'Ativo' WHERE id = ?", (nova_data, m_id))
            conn.commit()
            st.success(f"✅ Tempo atualizado! Nova expiração: {nova_data}")
            st.balloons()
    else:
        st.info("Não há clientes ativos ou expirados para gerenciar.")
