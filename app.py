import streamlit as st
import telebot
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import time

# --- CONFIGURAÇÕES INICIAIS ---
TOKEN = '8506261472:AAEFl-coVYJtnVjlILf04n5WJlaMNgqDv84'
bot = telebot.TeleBot(TOKEN)

# --- FUNÇÕES DE BANCO DE DADOS ---
def conectar():
    conn = sqlite3.connect('vanthagem.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS membros 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    grupo_id TEXT, grupo_nome TEXT, 
                    user_id TEXT, nome TEXT, 
                    entrada TEXT, saida TEXT)''')
    conn.commit()
    return conn

conn = conectar()

# --- INTERFACE STREAMLIT (O SITE) ---
st.set_page_config(page_title="Vanthagem Assinaturas", layout="wide")

st.sidebar.title("💎 Vanthagem Assinaturas")
aba = st.sidebar.radio("Navegação", ["Dashboard Geral", "Gerenciar Grupos", "Adicionar Membro"])

if aba == "Dashboard Geral":
    st.title("📊 Painel de Controle")
    
    # Carregar dados
    df = pd.read_sql_query("SELECT * FROM membros", conn)
    
    if not df.empty:
        # Cálculo de tempo restante
        def calcular_restante(data_saida):
            if data_saida == "Vitalício": return 9999
            saida = datetime.strptime(data_saida, "%d/%m/%Y %H:%M")
            restante = saida - datetime.now()
            return restante.total_seconds() / 3600 # Retorna em horas

        df['Horas_Restantes'] = df['saida'].apply(calcular_restante)

        # FUNÇÃO DO FUNDO VERMELHO (Sua exigência principal)
        def style_red(row):
            if row.Horas_Restantes <= 24:
                return ['background-color: #ff4d4d; color: white'] * len(row)
            return [''] * len(row)

        # Exibição da Tabela
        st.subheader("Lista de Membros Ativos")
        st.write("Linhas em vermelho indicam expiração em menos de 24h.")
        
        # Limpando a tabela para exibição
        display_df = df[['grupo_nome', 'nome', 'entrada', 'saida']].copy()
        display_df.columns = ['Grupo', 'Cliente', 'Data de Entrada', 'Data de Expiração']
        
        st.table(display_df.style.apply(style_red, axis=1))
    else:
        st.info("Nenhum membro cadastrado ainda.")

elif aba == "Adicionar Membro":
    st.title("➕ Novo Assinante")
    
    with st.form("form_add"):
        g_id = st.text_input("ID do Grupo (Ex: -100...)")
        g_nome = st.text_input("Nome do Grupo")
        u_id = st.text_input("ID do Usuário (ou use link de uso único)")
        u_nome = st.text_input("Nome do Cliente")
        tempo_opcoes = ["30 min", "1 hora", "15 dias", "30 dias", "1 ano", "Vitalício"]
        tempo = st.selectbox("Duração da Assinatura", tempo_opcoes)
        
        enviar = st.form_submit_button("Confirmar Cadastro")
        
        if enviar:
            agora = datetime.now()
            # Lógica de cálculo de data
            if tempo == "30 min": expira = agora + timedelta(minutes=30)
            elif tempo == "1 hora": expira = agora + timedelta(hours=1)
            elif tempo == "15 dias": expira = agora + timedelta(days=15)
            elif tempo == "30 dias": expira = agora + timedelta(days=30)
            elif tempo == "1 ano": expira = agora + timedelta(days=365)
            else: expira = "Vitalício"
            
            data_entrada = agora.strftime("%d/%m/%Y %H:%M")
            data_saida = expira.strftime("%d/%m/%Y %H:%M") if expira != "Vitalício" else "Vitalício"
            
            cursor = conn.cursor()
            cursor.execute("INSERT INTO membros (grupo_id, grupo_nome, user_id, nome, entrada, saida) VALUES (?,?,?,?,?,?)",
                           (g_id, g_nome, u_id, u_nome, data_entrada, data_saida))
            conn.commit()
            st.success(f"Cliente {u_nome} adicionado com sucesso!")

# --- LOOP DE REMOÇÃO AUTOMÁTICA (Roda por trás do site) ---
# Aqui o bot checa o banco e expulsa quem expirou
