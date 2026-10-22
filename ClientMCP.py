import asyncio
import json
import csv
import time
import requests
from datetime import datetime
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

# ==========================================
# 1. CONFIGURAÇÕES
# ==========================================
OPENROUTER_API_KEY = "COLOQUE_SUA_CHAVE_OPENROUTER_AQUI"
NODE_RED_URL = "http://3.90.6.151:1880"
#MODELO_IA = "nvidia/nemotron-3.5-lightning:free"
#MODELO_IA= "anthropic/claude-sonnet-5"
#MODELO_IA = "~deepseek/deepseek-v4-flash-latest"
MODELO_IA = "openai/gpt-4o-mini"

# ==========================================
# 2. CONTROLE DA PLANTA (NODE-RED)
# ==========================================
def injetar_falha(tipo_falha):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚨 INJETANDO DISTÚRBIO: {tipo_falha.upper()}...")
    requests.get(f"{NODE_RED_URL}/{tipo_falha}")

def normalizar_planta():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Normalizando a planta...")
    requests.get(f"{NODE_RED_URL}/normalizar")
    print("Aguardando 130s para a malha estabilizar para o próximo ciclo...\n")
    time.sleep(130)

# ==========================================
# 3. TRADUTOR DE FERRAMENTAS (MCP -> OPENROUTER)
# ==========================================
def formatar_ferramentas_para_ia(mcp_tools):
    ferramentas_ia = []
    for tool in mcp_tools.tools:
        parametros = tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}}
        ferramentas_ia.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": parametros
            }
        })
    return ferramentas_ia

# ==========================================
# 4. O AGENTE INVESTIGADOR (O CÉREBRO)
# ==========================================
async def investigar_planta_com_agente(session: ClientSession):
    """Roda o loop de raciocínio da IA, calculando latência e tokens consumidos"""
    
    mcp_tools_list = await session.list_tools()
    ferramentas_disponiveis = formatar_ferramentas_para_ia(mcp_tools_list)
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    mensagens = [
        {
            "role": "system", 
            "content": "Você é um Agente de Diagnóstico Industrial autônomo. Sua tarefa é monitorar e diagnosticar uma malha de controle PID de nível de um tanque de líquidos(composta pelo tanque, bomba(atuador), Sensor de nivél).\n\nVocê tem acesso a ferramentas via Model Context Protocol (MCP).\n\nSua ÚLTIMA resposta deve ser OBRIGATORIAMENTE E APENAS um JSON estrito no formato: {'falha': 'nome_da_falha_ou_normal', 'confianca': 0.95}"
        },
        {
            "role": "user", 
            "content": "Inicie a investigação do sistema, colete os dados necessários usando suas ferramentas e emita o diagnóstico final."
        }
    ]
    
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    inicio_tempo = time.time()
    
    for interacao in range(8):
        payload = {
            "model": MODELO_IA,
            "messages": mensagens,
            "tools": ferramentas_disponiveis
        }
        
        resposta = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        
        if resposta.status_code != 200:
            print(f"\n[ERRO DA API DO OPENROUTER - STATUS {resposta.status_code}]:\n{resposta.text}")
            return '{"erro": "A API rejeitou a requisição"}', 0, 0, 0, 0
            
        resposta_json = resposta.json()
        
        uso_tokens = resposta_json.get('usage', {})
        total_prompt_tokens += uso_tokens.get('prompt_tokens', 0)
        total_completion_tokens += uso_tokens.get('completion_tokens', 0)
        
        mensagem_ia = resposta_json['choices'][0]['message']
        
        if 'tool_calls' in mensagem_ia and mensagem_ia['tool_calls']:
            mensagens.append(mensagem_ia)
            for tool_call in mensagem_ia['tool_calls']:
                nome_ferramenta = tool_call['function']['name']
                argumentos = json.loads(tool_call['function']['arguments'])
                print(f" [AGENTE] Solicitou execução da ferramenta: {nome_ferramenta}...")
                
                resultado = await session.call_tool(nome_ferramenta, argumentos)
                texto_resultado = resultado.content[0].text
                
                mensagens.append({
                    "role": "tool",
                    "tool_call_id": tool_call['id'],
                    "name": nome_ferramenta,
                    "content": texto_resultado
                })
        else:
            laudo = mensagem_ia.get('content', '')
            print(f"\n [DIAGNÓSTICO FINAL]: {laudo}")
            
            fim_tempo = time.time()
            latencia_total = round(fim_tempo - inicio_tempo, 2)
            total_tokens = total_prompt_tokens + total_completion_tokens
            
            return laudo, latencia_total, total_prompt_tokens, total_completion_tokens, total_tokens

    fim_tempo = time.time()
    latencia_total = round(fim_tempo - inicio_tempo, 2)
    total_tokens = total_prompt_tokens + total_completion_tokens
    return '{"erro": "Não conseguiu diagnosticar a tempo"}', latencia_total, total_prompt_tokens, total_completion_tokens, total_tokens

# ==========================================
# 5. O GERENCIADOR DO BENCHMARK
# ==========================================
async def rodar_benchmark():
    print("=== INICIANDO LABORATÓRIO TCC (MODO MCP AUTÔNOMO) ===")
    cenario = "normalizar" # Alteração dos cenários (ex: falha-sensor)
    
    server_params = StdioServerParameters(command="python", args=["ServidorMCP.py"])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[SISTEMA] Conectado com sucesso ao Servidor MCP local!")
            
            # Criando o CSV com as novas colunas de métricas
            with open('resultados_tcc_OpenIA_Normal.csv', mode='w', newline='', encoding='utf-8') as arquivo_csv:
                escritor = csv.writer(arquivo_csv)
                escritor.writerow([
                    'Ciclo', 
                    'Falha_Injetada', 
                    'Laudo_IA', 
                    'Latencia_s', 
                    'Tokens_Prompt', 
                    'Tokens_Completion', 
                    'Tokens_Total', 
                    'Horario'
                ])
                
                # Definindo 10 ciclos de teste para a base de dados
                for ciclo in range(1, 11):
                    print(f"\n--- INICIANDO CICLO {ciclo} ---")
                    
                    print("⏳ Operando em regime nominal (40s)...")
                    time.sleep(40)
                    
                    injetar_falha(cenario)
                    
                    print("⏳ Aguardando a falha refletir na dinâmica da planta (40s)...")
                    time.sleep(40)
                    
                    print("\n🤖 Acordando o Agente IA para investigar o sistema...")
                    # Agente é chamado sem envio de logs. Ele se vira com as ferramentas!
                    laudo_bruto, latencia, t_prompt, t_completion, t_tokens = await investigar_planta_com_agente(session)
        
                    # ====TRAVA DE SEGURANÇA=====
                    if laudo_bruto is None:
                        laudo_bruto = '{"falha": "erro_modelo_sem_resposta", "confianca": 0.0}'
                        print(" [ALERTA] A IA retornou um conteúdo vazio neste ciclo.")
            
                    # Limpa quebras de linha do laudo da IA para evitar quebrar o layout do CSV
                    # Adicione o str() aqui também para garantir!
                    laudo_sanitizado = str(laudo_bruto).replace('\n', ' ').replace('\r', ' ')
                    
                    # Escreve a linha limpa e estruturada na planilha
                    escritor.writerow([
                        ciclo, 
                        cenario, 
                        laudo_sanitizado, 
                        latencia, 
                        t_prompt, 
                        t_completion, 
                        t_tokens, 
                        datetime.now().strftime('%H:%M:%S')
                    ])
                    
                    normalizar_planta()

if __name__ == "__main__":
    asyncio.run(rodar_benchmark())