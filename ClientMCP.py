import asyncio
import json
import csv
import time
import random
import requests
from datetime import datetime
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

# ==========================================
# 1. CONFIGURAÇÕES
# ==========================================
OPENROUTER_API_KEY = "COLE-SUA-CHAVE-AQUI"
NODE_RED_URL = "http://3.83.237.51:1880"
MODELO_IA = "nvidia/nemotron-3.5-lightning:free"
#MODELO_IA= "anthropic/claude-sonnet-5"
#MODELO_IA = "~deepseek/deepseek-v4-flash-latest"
#MODELO_IA = "openai/gpt-4o-mini"

# ==========================================
# 2. CONTROLE DA PLANTA (NODE-RED)
# ==========================================
def injetar_falha(tipo_falha):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚨 INJETANDO DISTÚRBIO: {tipo_falha.upper()}...")
    requests.get(f"{NODE_RED_URL}/{tipo_falha}")

def normalizar_planta():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Normalizando a planta...")
    requests.get(f"{NODE_RED_URL}/normalizar")
    print("Aguardando 200s para a malha estabilizar para o próximo ciclo...\n")
    time.sleep(200)

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
                "content": (
                    "Você é um Agente de Diagnóstico Industrial autônomo. "
                    "Sua tarefa é monitorar e diagnosticar uma malha de controle PID de nível de um tanque de líquidos (composto pelo tanque, bomba e sensor de nível).\n\n"
                    "Você tem acesso a ferramentas via Model Context Protocol (MCP).\n\n"
                    "**DIRETRIZES FÍSICAS PARA DIAGNÓSTICO:**\n"
                    "1. **Analise a relação entre PV e CV:** Mesmo que o nível (PV) esteja estabilizado no SetPoint (SP), verifique se houve mudança brusca no esforço de controle (CV) em relação ao patamar nominal recente.\n"
                    "2. **Vazamento:** Se o PV estabiliza no SP (ou próximo dele), mas a CV precisa subir e se manter em um patamar anormalmente alto para sustentar esse nível, a bomba está compensando uma perda de fluido.\n"
                    "3. **Falha de Bomba:** Se o PV cai continuamente em rampa sem estabilizar enquanto a CV satura no limite máximo (250) sem conseguir repor o nível, há pane no atuador (bomba sem vazão).\n"
                    "4. **Falha de Sensor:** Um tanque não esvazia instantaneamente por gravidade. Uma queda abrupta do PV diretamente para 0.0 em um único passo de leitura é fisicamente impossível e indica perda de sinal ou falha no sensor.\n\n"
                    "O diagnóstico OBRIGATORIAMENTE deve ser UMA destas classes exatas: 'normal', 'falha_bomba', 'falha_sensor', 'vazamento' ou 'indeterminado'.\n"
                    "Sua ÚLTIMA resposta deve ser OBRIGATORIAMENTE E APENAS um objeto JSON estrito com o seguinte formato:\n"
                    "{\n"
                    '  "classe": "uma das classes permitidas",\n'
                    '  "confianca": "alta, media ou baixa",\n'
                    '  "evidencias": "Valores de PV, CV e SP que justificam a classe",\n'
                    '  "acao_recomendada": "Ação a ser tomada pelo operador"\n'
                    "}"
                )
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
    print("=== INICIANDO LABORATÓRIO TCC (MODO MCP AUTÔNOMO - TESTE CEGO) ===")
    
    # Define a quantidade de cada cenário (10 de cada, totalizando 40 testes)
    cenarios = (
        ["falha-bomba"] * 10 + 
        ["falha-sensor"] * 10 + 
        ["vazamento"] * 10 + 
        ["normalizar"] * 10
    )
    
    # Embaralha os cenários aleatoriamente para garantir o teste cego (blind test)
    random.shuffle(cenarios)
    
    server_params = StdioServerParameters(command="python", args=["ServidorMCP.py"])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[SISTEMA] Conectado com sucesso ao Servidor MCP local!")
            
            # Criando o CSV com as colunas de métricas para a análise estatística
            with open('resultados_tcc_TesteCego_Nvidiat2.csv', mode='w', newline='', encoding='utf-8') as arquivo_csv:
                escritor = csv.writer(arquivo_csv)
                escritor.writerow([
                    'Ciclo', 
                    'Falha_Injetada_Real', 
                    'Laudo_IA', 
                    'Latencia_s', 
                    'Tokens_Prompt', 
                    'Tokens_Completion', 
                    'Tokens_Total', 
                    'Horario'
                ])
                
                # O loop itera sobre a lista de 40 cenários já embaralhada
                for ciclo, cenario_atual in enumerate(cenarios, start=1):
                    print(f"\n--- INICIANDO CICLO {ciclo} DE {len(cenarios)} ---")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Cenário Sorteado Internamente: {cenario_atual} (Agente não sabe disso)")
                    
                    print("⏳ Operando em regime nominal (50s)...")
                    time.sleep(50)
                    
                    # Chama a injeção diretamente para qualquer cenário (incluindo o normal)
                    injetar_falha(cenario_atual)
                    
                    print("⏳ Aguardando a dinâmica da planta (50s)...")
                    time.sleep(50)
                    
                    print("\n🤖 Acordando o Agente IA para investigar o sistema às cegas...")
                    # Agente é chamado sem envio de logs. Ele se vira com as ferramentas!
                    laudo_bruto, latencia, t_prompt, t_completion, t_tokens = await investigar_planta_com_agente(session)
        
                    # ====TRAVA DE SEGURANÇA=====
                    if laudo_bruto is None:
                        laudo_bruto = '{"classe": "sem_laudo", "confianca": "baixa", "evidencias": "Nenhuma", "acao_recomendada": "Nenhuma"}'
                        print(" [ALERTA] A IA retornou um conteúdo vazio neste ciclo.")
            
                    # Limpa quebras de linha do laudo da IA para evitar quebrar o layout do CSV
                    laudo_sanitizado = str(laudo_bruto).replace('\n', ' ').replace('\r', ' ')
                    
                    # Escreve a linha limpa e estruturada na planilha
                    escritor.writerow([
                        ciclo, 
                        cenario_atual, 
                        laudo_sanitizado, 
                        latencia, 
                        t_prompt, 
                        t_completion, 
                        t_tokens, 
                        datetime.now().strftime('%H:%M:%S')
                    ])
                    
                    normalizar_planta()

if __name__ == "__main__":
    import asyncio
    asyncio.run(rodar_benchmark())