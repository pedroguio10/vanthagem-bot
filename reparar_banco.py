import sqlite3
import os

# Tenta encontrar o arquivo de banco de dados
bancos = [f for f in os.listdir('.') if f.endswith('.db')]
if not bancos:
    print("Nenhum arquivo .db encontrado.")
else:
    nome_banco = bancos[0]
    print(f"Tentando reparar: {nome_banco}")
    try:
        conn = sqlite3.connect(nome_banco)
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE membros ADD COLUMN status TEXT DEFAULT 'ativo'")
        conn.commit()
        conn.close()
        print("✅ Coluna 'status' adicionada!")
    except Exception as e:
        print(f"Erro: {e}")
