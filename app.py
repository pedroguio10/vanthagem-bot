import streamlit as st
import telebot
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import threading
import time

# =========================================================
# CONFIGURAÇÕES
# =========================================================

TOKEN = 'SEU_TOKEN_AQUI'
SENHA_APP = "29072004pP1!"

bot = telebot.TeleBot(TOKEN)

# =========================================================
# HORÁRIO BRASIL DEFINITIVO
# =========================================================

FUSO_BR = ZoneInfo("America/Sao_Paulo")

def get_now_br():
    return datetime.now(FUSO_BR)

# =========================================================
# LOGIN / SEGURANÇA
# =========================================================

if "logado" not in st.session_state:
    st.session_state.logado = False

if "tentativas" not in st.session_state:
    st.session_state.tentativas = 0

if "ultimo_erro" not in st.session_state:
    st.session_state.ultimo_erro = 0

if "bloqueado_ate" not in st.session_state:
    st.session_state.bloqueado_ate = None

# =========================================================
# TELA LOGIN
# =========================================================

if not st.session_state.logado:

    st.set_page_config(page_title="Login", layout="centered")

    st.title("🔐 Vanthagem PRO")

    agora_ts = time.time()

    # bloqueio 30 min
    if st.session_state.bloqueado_ate:

        restante = int(st.session_state.bloqueado_ate - agora_ts)

        if restante > 0:
            minutos = restante // 60
            segundos = restante % 60

            st.error(
                f"Sistema bloqueado temporariamente.\n\n"
                f"Tente novamente em {minutos}m {segundos}s"
            )

            st.stop()

    senha = st.text_input(
        "Digite a senha",
        type="password"
    )

    if st.button("ENTRAR"):

        # proteção flood 5 segundos
        if agora_ts - st.session_state.ultimo_erro < 5:
            st.warning("Espere 5 segundos antes de tentar novamente.")
            st.stop()

        if senha == SENHA_APP:

            st.session_state.logado = True
            st.session_state.tentativas = 0
            st.rerun()

        else:

            st.session_state.tentativas += 1
            st.session_state.ultimo_erro = agora_ts

            restantes = 4 - st.session_state.tentativas

            if st.session_state.tentativas >= 4:

                st.session_state.bloqueado_ate = agora_ts + (30 * 60)

                st.error(
                    "Muitas tentativas incorretas.\n\n"
                    "Sistema bloqueado por 30 minutos."
                )

                st.stop()

            else:

                st.error(
                    f"Senha incorreta.\n\n"
                    f"Tentativas restantes: {restantes}"
                )

    st.stop()

# =========================================================
# APP PRINCIPAL
# =========================================================

st.set_page_config(page_title="Vanthagem PRO", layout="wide")

# =========================================================
# BANCO
# =========================================================

def conectar():

    conn = sqlite3.connect(
        'vanthagem_v2.db',
        check_same_thread=False
    )

    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS membros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id TEXT,
            grupo_nome TEXT,
            user_id TEXT,
            nome TEXT,
            username TEXT,
            entrada TEXT,
            saida TEXT,
            duracao_txt TEXT,
            status TEXT,
            invite_link TEXT,
            telefone TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            nome TEXT,
            acao TEXT,
            grupo_nome TEXT,
            data_hora TEXT,
            detalhes TEXT
        )
    ''')

    conn.commit()

    return conn

conn = conectar()

# =========================================================
# FORMATAÇÃO DATA BR
# =========================================================

def formatar_data_br(valor):

    if not valor:
        return valor

    if valor in [
        "Vitalício",
        "Aguardando",
        "Aguardando Entrada",
        "Não Iniciado"
    ]:
        return valor

    try:

        if "-" in valor:

            dt = pd.to_datetime(valor)

            if dt.tzinfo is None:
                dt = dt.tz_localize("UTC")

            dt = dt.tz_convert("America/Sao_Paulo")

            return dt.strftime("%d/%m/%Y %H:%M")

        return valor

    except:
        return valor

# =========================================================
# MONITORAMENTO
# =========================================================

def monitor_geral():

    while True:

        try:

            conn_thread = sqlite3.connect('vanthagem_v2.db')
            cursor = conn_thread.cursor()

            agora = get_now_br()

            cursor.execute("""
                SELECT
                    id,
                    grupo_id,
                    user_id,
                    nome,
                    saida,
                    grupo_nome
                FROM membros
                WHERE status = 'Ativo'
            """)

            ativos = cursor.fetchall()

            for m in ativos:

                m_id, g_id, u_id, nome, data_saida, g_nome = m

                if data_saida == "Vitalício":
                    continue

                try:

                    limite = datetime.strptime(
                        data_saida,
                        "%d/%m/%Y %H:%M"
                    ).replace(tzinfo=FUSO_BR)

                    if agora >= limite:

                        try:
                            bot.ban_chat_member(g_id, u_id)
                            bot.unban_chat_member(g_id, u_id)
                        except:
                            pass

                        cursor.execute("""
                            UPDATE membros
                            SET status = 'Expirado'
                            WHERE id = ?
                        """, (m_id,))

                        data_str = agora.strftime("%d/%m/%Y %H:%M")

                        cursor.execute("""
                            INSERT INTO historico
                            (
                                user_id,
                                nome,
                                acao,
                                grupo_nome,
                                data_hora,
                                detalhes
                            )
                            VALUES (?,?,?,?,?,?)
                        """, (
                            u_id,
                            nome,
                            "Expirou/Saiu",
                            g_nome,
                            data_str,
                            f"Tempo finalizado ({data_saida})"
                        ))

                        conn_thread.commit()

                except:
                    continue

            conn_thread.close()

        except:
            pass

        time.sleep(30)

# =========================================================
# ENTRADA MEMBRO
# =========================================================

@bot.chat_member_handler()
def monitorar_entrada(message):

    new_member = message.new_chat_member

    if new_member.status == 'member':

        u_id = str(new_member.user.id)
        g_id = str(message.chat.id)

        conn_in = sqlite3.connect('vanthagem_v2.db')

        cursor = conn_in.cursor()

        cursor.execute("""
            SELECT
                id,
                duracao_txt,
                nome,
                grupo_nome
            FROM membros
            WHERE user_id = ?
            AND grupo_id = ?
            AND status = 'Pendente'
        """, (u_id, g_id))

        res = cursor.fetchone()

        if res:

            m_id, duracao, nome, g_nome = res

            agora = get_now_br()

            deltas = {
                "30 minutos": timedelta(minutes=30),
                "1 hora": timedelta(hours=1),
                "1 semana": timedelta(weeks=1),
                "15 dias": timedelta(days=15),
                "30 dias": timedelta(days=30),
                "60 dias": timedelta(days=60),
                "90 dias": timedelta(days=90),
                "1 ano": timedelta(days=365),
                "2 anos": timedelta(days=730)
            }

            data_entrada = agora.strftime("%d/%m/%Y %H:%M")

            if duracao != "Vitalício":
                data_saida = (
                    agora + deltas[duracao]
                ).strftime("%d/%m/%Y %H:%M")
            else:
                data_saida = "Vitalício"

            cursor.execute("""
                UPDATE membros
                SET entrada = ?,
                    saida = ?,
                    status = 'Ativo'
                WHERE id = ?
            """, (
                data_entrada,
                data_saida,
                m_id
            ))

            conn_in.commit()

        conn_in.close()

# =========================================================
# THREADS
# =========================================================

if "bot_rodando" not in st.session_state:

    bot.remove_webhook()

    threading.Thread(
        target=monitor_geral,
        daemon=True
    ).start()

    threading.Thread(
        target=lambda: bot.infinity_polling(
            allowed_updates=['chat_member', 'message'],
            skip_pending=True
        ),
        daemon=True
    ).start()

    st.session_state.bot_rodando = True

# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title("💎 Vanthagem PRO")

if st.sidebar.button("🚪 Logout"):

    st.session_state.logado = False
    st.rerun()

# =========================================================
# DASHBOARD
# =========================================================

st.title("📊 Gestão de Membros")

df = pd.read_sql_query("""
    SELECT
        grupo_nome,
        nome,
        username,
        status,
        entrada,
        saida
    FROM membros
""", conn)

if not df.empty:

    df['entrada'] = df['entrada'].apply(formatar_data_br)
    df['saida'] = df['saida'].apply(formatar_data_br)

    st.dataframe(df, width='stretch')

else:

    st.info("Nenhum dado encontrado.")
